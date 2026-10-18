# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Autostart and the background process on Windows.

Linux supervises the background mode (``multazem --headless``) with a ``systemd --user`` unit (see
:mod:`multazem.services.systemd_service`). Windows has no per-user service manager that works without
administrator rights, so two simple things take its place:

* A value in the per-user ``Run`` registry key makes Windows start the background process at every login.
  That is what "enabled" means here.
* The background process holds a lock file for as long as it runs and writes its process id beside it. That is
  how the window can tell that the process is running ("active") and how it is stopped again.

The functions have the same names and results as those of the systemd module, so the interface does not care
which one it talks to.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

from ..i18n import tr
from ..logs import get_logger
from .paths import local_data_dir, log_file
from .process_lock import ProcessLock

logger = get_logger("service")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "Multazem"
PRESENCE_LOCK_NAME = "background.lock"
PRESENCE_PID_NAME = "background.pid"

# How long to wait for the background process to start or to stop, and how often to look.
START_TIMEOUT_SECONDS = 15.0
STOP_TIMEOUT_SECONDS = 5.0
POLL_INTERVAL_SECONDS = 0.1
# Another background process may be probing the lock for an instant; asking again settles that.
CLAIM_ATTEMPTS = 5

# Process creation flags: no console and not tied to the console of the process that starts it.
_DETACHED_PROCESS = 0x00000008
_CREATE_NEW_PROCESS_GROUP = 0x00000200


def _presence_lock_path() -> Path:
    """Returns the lock file that the running background process holds."""
    return local_data_dir() / PRESENCE_LOCK_NAME


def _presence_pid_path() -> Path:
    """Returns the file in which the running background process records its process id."""
    return local_data_dir() / PRESENCE_PID_NAME


def background_command() -> list[str]:
    """Returns the command that starts the background mode.

    It uses the interpreter that runs the application, preferring ``pythonw.exe`` of the same environment
    because it opens no console window.
    """
    interpreter = Path(sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    if interpreter.name.lower() == "python.exe" and windowless.is_file():
        interpreter = windowless
    return [str(interpreter), "-m", "multazem", "--headless"]


# --- The Run registry value ---


def _read_run_value() -> str | None:
    """Returns the command Windows starts at login, or ``None`` when autostart is off."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        return None
    return str(value)


def _write_run_value(command_line: str) -> None:
    """Makes Windows start ``command_line`` at login.

    Raises:
        OSError: When the registry cannot be written.
    """
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, command_line)


def _delete_run_value() -> None:
    """Stops Windows from starting the application at login; succeeds when nothing was set."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, RUN_VALUE_NAME)
    except FileNotFoundError:
        return


# --- The running background process ---


def service_is_enabled() -> bool:
    """Returns whether the background process is started at login."""
    try:
        return _read_run_value() is not None
    except OSError as error:
        logger.warning("Could not read the autostart setting: %s", error)
        return False


def service_is_active() -> bool:
    """Returns whether the background process is running right now.

    The answer comes from its lock file: taking the lock for an instant succeeds only when nobody holds it.
    """
    probe = ProcessLock(_presence_lock_path())
    if probe.acquire():
        probe.release()
        return False
    return True


@contextlib.contextmanager
def background_process_presence() -> Iterator[bool]:
    """Marks the calling process as *the* background process for as long as the block runs.

    It takes the lock that :func:`service_is_active` probes and records the process id so that
    :func:`service_uninstall` can stop the process. Both are undone when the block ends.

    Yields:
        ``True`` when this process may run as the background process, ``False`` when another one already does.
    """
    with contextlib.suppress(OSError):
        local_data_dir().mkdir(parents=True, exist_ok=True)
    lock = ProcessLock(_presence_lock_path())
    claimed = False
    for attempt in range(CLAIM_ATTEMPTS):
        claimed = lock.acquire()
        if claimed or attempt == CLAIM_ATTEMPTS - 1:
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    if claimed:
        with contextlib.suppress(OSError):
            _presence_pid_path().write_text(str(os.getpid()), encoding="ascii")
    try:
        yield claimed
    finally:
        if claimed:
            with contextlib.suppress(OSError):
                _presence_pid_path().unlink(missing_ok=True)
            lock.release()


def _start_background_process(command: list[str]) -> tuple[bool, str]:
    """Starts the background process unless it is running, and waits until it has claimed its lock.

    Returns:
        ``(started, reason)``; the reason is empty on success.
    """
    if service_is_active():
        return True, ""
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=_DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP,
        )
    except OSError as error:
        return False, str(error)
    deadline = time.monotonic() + START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if service_is_active():
            return True, ""
        code = process.poll()
        if code is not None:
            return False, f"the background process exited with code {code} (see {log_file()})"
        time.sleep(POLL_INTERVAL_SECONDS)
    return False, f"the background process did not start within {START_TIMEOUT_SECONDS:g} seconds (see {log_file()})"


def _stop_background_process() -> None:
    """Ends the running background process, if there is one, and waits for it to let go of its lock."""
    try:
        pid = int(_presence_pid_path().read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        pid = None
    if pid is not None and service_is_active():
        # On Windows any signal but Ctrl+C and Ctrl+Break ends the process at once; it needs no clean-up
        # because its lock is released by the system.
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
        while service_is_active() and time.monotonic() < deadline:
            time.sleep(POLL_INTERVAL_SECONDS)
    with contextlib.suppress(OSError):
        _presence_pid_path().unlink(missing_ok=True)


# --- What the window and the start-up code call ---


def service_install() -> tuple[bool, str]:
    """Turns autostart on and starts the background process now.

    Returns:
        ``(succeeded, message for the user)``. When the process cannot be started, autostart is turned off
        again.
    """
    command = background_command()
    try:
        _write_run_value(subprocess.list2cmdline(command))
    except OSError as error:
        return False, tr("service.error.write_failed", detail=error)
    started, reason = _start_background_process(command)
    if not started:
        with contextlib.suppress(OSError):
            _delete_run_value()
        return False, tr("service.error.enable_failed", detail=reason)
    return True, tr("service.installed")


def service_uninstall() -> tuple[bool, str]:
    """Turns autostart off and stops the background process.

    Returns:
        ``(succeeded, message for the user)``.
    """
    try:
        _delete_run_value()
    except OSError as error:
        return False, tr("service.error.remove_failed", detail=error)
    _stop_background_process()
    return True, tr("service.uninstalled")


def refresh_autostart() -> bool:
    """Points the autostart command at the installation that is running now.

    The command is written when autostart is turned on, so it goes stale when the program is moved or
    reinstalled with another Python.

    Returns:
        ``True`` when the stored command was out of date and has been replaced.
    """
    try:
        stored = _read_run_value()
        current = subprocess.list2cmdline(background_command())
        if stored is None or stored == current:
            return False
        _write_run_value(current)
    except OSError as error:
        logger.warning("Could not refresh the autostart command: %s", error)
        return False
    logger.info("Autostart now starts %s", current)
    return True
