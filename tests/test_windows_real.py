# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The Windows code against the real Windows: the registry, file locks, named mutexes and a real background process.

The other Windows tests use stand-ins for all of this, so that they run anywhere. These run only on Windows and only
when ``MULTAZEM_REAL_WINDOWS_TESTS=1`` is set (the Windows CI job sets it), because they write the sign-in entry of the
reminders and the notification identity of the program into the registry of whoever runs them.
"""

import contextlib
import os
import sys
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or os.environ.get("MULTAZEM_REAL_WINDOWS_TESTS") != "1",
    reason="needs Windows and MULTAZEM_REAL_WINDOWS_TESTS=1 (it changes the registry of the user who runs it)",
)

WAIT_SECONDS = 20


def wait_until(condition, seconds: float = WAIT_SECONDS) -> bool:
    """Returns whether ``condition()`` became true within ``seconds``."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.2)
    return condition()


@pytest.fixture
def private_profile(tmp_path, monkeypatch):
    """Points the program's folders at the test's directory, and lets what it starts find GTK where it is now."""
    from multazem import winsupport

    runtime = winsupport.find_gtk_runtime()
    if runtime is not None:
        monkeypatch.setenv("MULTAZEM_GTK_DIR", str(runtime))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    return tmp_path


def test_two_file_locks_exclude_each_other_and_a_released_one_can_be_taken_again(tmp_path):
    from multazem.services.process_lock import ProcessLock

    path = tmp_path / "test.lock"
    first, second = ProcessLock(path), ProcessLock(path)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_a_second_copy_finds_the_mutex_and_wakes_the_first(monkeypatch):
    from multazem.services import single_instance

    monkeypatch.setattr(single_instance, "MUTEX_NAME", f"Local\\Multazem.Test.{os.getpid()}")
    monkeypatch.setattr(single_instance, "EVENT_NAME", f"Local\\Multazem.Test.Activate.{os.getpid()}")
    first, second = single_instance.SingleInstance(), single_instance.SingleInstance()
    assert first.acquire()
    woken = threading.Event()
    first.listen(woken.set)
    assert not second.acquire()
    assert second.request_activation()
    assert woken.wait(WAIT_SECONDS), "the first copy was not asked to show its window"


def test_the_background_reminders_turn_on_and_off_with_a_real_process(private_profile):
    from multazem.services import windows_service as service

    pid_file = Path(os.environ["LOCALAPPDATA"]) / "multazem" / service.PRESENCE_PID_NAME
    # Whatever an earlier run of the suite left behind.
    service.service_uninstall()
    try:
        started, text = service.service_install()
        assert started, text
        assert service.service_is_enabled()
        assert service.service_is_active()
        assert wait_until(pid_file.exists), "the background process recorded no process id"
        process_id = pid_file.read_text(encoding="ascii").strip()
        assert process_id.isdigit()

        # Turning them on again leaves the one process alone.
        again, text = service.service_install()
        assert again, text
        assert pid_file.read_text(encoding="ascii").strip() == process_id
    finally:
        stopped, text = service.service_uninstall()
    assert stopped, text
    assert wait_until(lambda: not service.service_is_active()), "the background process is still running"
    assert not service.service_is_enabled()
    assert not pid_file.exists()


def test_the_toast_identity_is_registered_and_powershell_runs_the_toast_script(private_profile):
    import winreg

    from multazem.services import windows_toast

    key_path = rf"Software\Classes\AppUserModelId\{windows_toast.APP_USER_MODEL_ID}"
    try:
        _shown, reason = windows_toast.send_toast("Multazem", "test")
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            assert winreg.QueryValueEx(key, "DisplayName")[0]
    finally:
        with contextlib.suppress(OSError):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    # Whether a toast can be shown depends on the desktop of the machine (a build machine may have none), but a script
    # that PowerShell cannot even parse or run is a mistake of the program.
    for mistake in ("ParserError", "Unable to find type", "is not recognized", "powershell.exe was not found"):
        assert mistake not in reason, reason
