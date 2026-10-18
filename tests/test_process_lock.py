# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The single-notifier lock: the Windows implementation, checked here with a fake ``msvcrt``."""

import errno
import sys
import types

import pytest

from multazem.services import process_lock
from multazem.services.process_lock import ProcessLock, default_lock_path


class FakeMsvcrt(types.ModuleType):
    """A stand-in for ``msvcrt`` whose byte-range lock is held by whoever locked first."""

    LK_NBLCK = 2
    LK_UNLCK = 0

    def __init__(self):
        super().__init__("msvcrt")
        self.holder = None
        self.calls = []
        self.failure = None

    def locking(self, descriptor, mode, nbytes):
        """Locks one byte, or fails the way Windows does while another handle holds it."""
        self.calls.append((mode, nbytes))
        if self.failure is not None:
            raise self.failure
        if self.holder is not None and self.holder != descriptor:
            raise OSError(errno.EACCES, "Permission denied")
        self.holder = descriptor


@pytest.fixture
def windows_lock(monkeypatch):
    """Makes the lock code take the Windows branch with a fake ``msvcrt``; returns the fake."""
    fake = FakeMsvcrt()
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(process_lock, "is_windows", lambda: True)
    return fake


def test_the_windows_lock_is_in_the_temp_directory_of_the_user(windows_lock, tmp_path, monkeypatch):
    monkeypatch.setattr(process_lock.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    assert default_lock_path() == tmp_path / "tmp" / "multazem.lock"


def test_the_windows_lock_takes_the_first_byte_without_waiting(windows_lock, tmp_path):
    lock = ProcessLock(tmp_path / "x.lock")
    assert lock.acquire() is True
    assert windows_lock.calls == [(FakeMsvcrt.LK_NBLCK, 1)]
    lock.release()


def test_a_range_held_by_another_handle_blocks_the_lock(windows_lock, tmp_path):
    first = ProcessLock(tmp_path / "x.lock")
    second = ProcessLock(tmp_path / "x.lock")
    assert first.acquire() is True
    windows_lock.holder = -1  # a handle of another process
    assert second.acquire() is False
    first.release()


@pytest.mark.parametrize("code", [errno.EACCES, errno.EDEADLK])
def test_both_errors_that_windows_uses_for_a_held_range_mean_blocked(windows_lock, tmp_path, code):
    windows_lock.failure = OSError(code, "held")
    assert ProcessLock(tmp_path / "x.lock").acquire() is False


def test_any_other_error_lets_the_process_run_anyway(windows_lock, tmp_path):
    windows_lock.failure = OSError(errno.EIO, "disk error")
    assert ProcessLock(tmp_path / "x.lock").acquire() is True


def test_the_lock_file_is_not_inherited_by_child_processes(tmp_path, monkeypatch):
    opened = []
    real_open = process_lock.os.open
    no_inherit = 0x40000000  # Windows' O_NOINHERIT is 0x80; on Linux that value means something else
    monkeypatch.setattr(process_lock.os, "O_NOINHERIT", no_inherit, raising=False)

    def recording_open(path, flags, mode):
        opened.append(flags)
        return real_open(path, flags & ~no_inherit, mode)

    monkeypatch.setattr(process_lock.os, "open", recording_open)
    lock = ProcessLock(tmp_path / "x.lock")
    assert lock.acquire() is True
    lock.release()
    assert opened[0] & no_inherit
