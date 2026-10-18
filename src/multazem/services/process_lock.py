# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Single-notifier lock shared by the GUI process and the background service.

Both processes run the same scheduler, but only one of them may send notifications at a
time or every prayer would be announced twice. The process holding an exclusive lock on a
file (``flock`` on Linux, ``msvcrt.locking`` on Windows) is the "leader"; the other keeps
retrying and takes over automatically as soon as the leader exits.
"""

from __future__ import annotations

import contextlib
import errno
import os
import tempfile
from pathlib import Path

from .paths import absolute_directory_from_environment, is_windows

LOCK_FILE_NAME = "multazem.lock"


def default_lock_path() -> Path:
    """Returns a lock path that resolves identically for the GUI and the service (same user).

    On Windows this is the temp directory, which already belongs to the current user. Elsewhere it prefers
    ``$XDG_RUNTIME_DIR`` (usually ``/run/user/<uid>``), then ``/run/user/<uid>`` itself, and falls back to the
    system temp directory when no writable runtime directory exists.
    """
    if is_windows():
        return Path(tempfile.gettempdir()) / LOCK_FILE_NAME
    candidates: list[Path] = []
    runtime = absolute_directory_from_environment("XDG_RUNTIME_DIR")
    if runtime is not None:
        candidates.append(runtime)
    candidates.append(Path(f"/run/user/{os.getuid()}"))
    for directory in candidates:
        if directory.is_dir() and os.access(directory, os.W_OK):
            return directory / LOCK_FILE_NAME
    return Path(tempfile.gettempdir()) / f"multazem-{os.getuid()}.lock"


def _try_lock(descriptor: int) -> bool:
    """Tries to lock the file without waiting.

    Args:
        descriptor: A file descriptor opened for writing.

    Returns:
        ``True`` when the lock was taken, ``False`` while another process holds it.

    Raises:
        OSError: When the lock could not be taken for any other reason.
    """
    if is_windows():
        return _try_lock_windows(descriptor)
    return _try_lock_posix(descriptor)


def _try_lock_posix(descriptor: int) -> bool:
    """Takes an exclusive ``flock``; see :func:`_try_lock`."""
    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _try_lock_windows(descriptor: int) -> bool:
    """Locks the first byte of the file with ``msvcrt.locking``; see :func:`_try_lock`.

    The lock covers a byte range, not the file, so the descriptor is moved to the start first. Windows reports
    a range that another process holds as ``EACCES`` (and as ``EDEADLOCK`` when it gave up waiting).
    """
    import msvcrt

    os.lseek(descriptor, 0, os.SEEK_SET)
    try:
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    except OSError as error:
        if error.errno in (errno.EACCES, errno.EDEADLK):
            return False
        raise
    return True


class ProcessLock:
    """An advisory, non-blocking, exclusive lock on a file.

    The lock is released when the process exits, however it exits, so a crashed leader never
    blocks the others. If the lock file cannot be used at all, :meth:`acquire` succeeds anyway: a
    duplicate notification is better than none.

    Args:
        path: The lock file; defaults to :func:`default_lock_path`.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._descriptor: int | None = None
        self._was_blocked = False
        self._takeover_pending = False

    @property
    def held(self) -> bool:
        """Whether this object currently holds the lock."""
        return self._descriptor is not None

    def acquire(self) -> bool:
        """Tries to become the leader; never blocks.

        Returns:
            ``True`` if this process may notify, ``False`` while another process holds the lock.
        """
        if self.held:
            return True
        descriptor = self._open_lock_file()
        if descriptor is None:
            return True
        try:
            locked = _try_lock(descriptor)
        except OSError:
            os.close(descriptor)
            return True
        if not locked:
            os.close(descriptor)
            self._was_blocked = True
            return False
        self._descriptor = descriptor
        # Getting the lock after having been blocked (rather than on a normal first start) means another
        # process just handed leadership over to us.
        self._takeover_pending = self._was_blocked
        self._was_blocked = False
        return True

    def _open_lock_file(self) -> int | None:
        """Opens (creating it if needed) the lock file for the current user only; ``None`` if that fails.

        The descriptor is not inherited by child processes: they would keep the lock alive after this process
        exited. Windows has no ``O_CLOEXEC``; its ``O_NOINHERIT`` does the same.
        """
        path = self._path or default_lock_path()
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOINHERIT", 0)
        try:
            return os.open(path, flags, 0o600)
        except OSError:
            return None

    def release(self) -> None:
        """Gives up the lock if it is held."""
        if self._descriptor is not None:
            with contextlib.suppress(OSError):
                os.close(self._descriptor)
            self._descriptor = None

    def consume_takeover(self) -> bool:
        """Returns ``True`` once after leadership was inherited from another process."""
        pending = self._takeover_pending
        self._takeover_pending = False
        return pending
