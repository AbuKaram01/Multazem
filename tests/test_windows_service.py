# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Autostart and the background process on Windows, checked with a fake registry and a fake process."""

import os
import signal
import subprocess
import sys

import pytest

from multazem.services import windows_service as svc

from windows_support import install_fake_winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


@pytest.fixture
def registry(monkeypatch):
    """A fake registry."""
    return install_fake_winreg(monkeypatch)


@pytest.fixture(autouse=True)
def private_state(tmp_path, monkeypatch):
    """Keeps the lock and process-id files of the background process inside the test's directory."""
    state = tmp_path / "state"
    monkeypatch.setattr(svc, "local_data_dir", lambda: state)
    monkeypatch.setattr(svc, "log_file", lambda: state / "multazem.log")
    monkeypatch.setattr(svc, "POLL_INTERVAL_SECONDS", 0.001)
    return state


class FakeProcess:
    """Stands in for the process that ``subprocess.Popen`` starts."""

    def __init__(self, exit_code=None):
        self.exit_code = exit_code

    def poll(self):
        """Returns the exit code, or ``None`` while the process runs."""
        return self.exit_code


def fake_popen(monkeypatch, *, claims_lock=True, exit_code=None):
    """Replaces ``subprocess.Popen`` of the service module.

    Args:
        monkeypatch: The test's ``monkeypatch`` fixture.
        claims_lock: Whether the started "process" takes the background lock the way the real one does.
        exit_code: The exit code the started "process" reports from its first poll on.

    Returns:
        ``(calls, presences)``: the recorded ``(command, kwargs)`` pairs and the presence contexts opened.
    """
    calls, presences = [], []

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        if claims_lock:
            presence = svc.background_process_presence()
            presence.__enter__()
            presences.append(presence)
        return FakeProcess(exit_code)

    monkeypatch.setattr(svc.subprocess, "Popen", popen)
    return calls, presences


def test_the_background_command_uses_the_windowless_interpreter_of_this_environment(tmp_path, monkeypatch):
    (tmp_path / "python.exe").write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    assert svc.background_command() == [str(tmp_path / "pythonw.exe"), "-m", "multazem", "--headless"]


def test_the_background_command_keeps_the_interpreter_when_there_is_no_windowless_one(tmp_path, monkeypatch):
    (tmp_path / "python.exe").write_text("")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    assert svc.background_command()[0] == str(tmp_path / "python.exe")


def test_autostart_is_off_until_it_is_turned_on(registry):
    assert svc.service_is_enabled() is False


def test_autostart_is_on_when_the_run_value_exists(registry):
    svc._write_run_value("x")
    assert svc.service_is_enabled() is True


def test_an_unreadable_registry_counts_as_off(registry, monkeypatch):
    def broken():
        raise PermissionError("denied")

    monkeypatch.setattr(svc, "_read_run_value", broken)
    assert svc.service_is_enabled() is False


def test_the_process_is_not_active_when_nothing_holds_the_lock():
    assert svc.service_is_active() is False


def test_the_process_is_active_while_it_holds_the_lock():
    with svc.background_process_presence() as claimed:
        assert claimed is True
        assert svc.service_is_active() is True
    assert svc.service_is_active() is False


def test_a_second_background_process_does_not_get_to_run(monkeypatch):
    monkeypatch.setattr(svc, "CLAIM_ATTEMPTS", 2)
    with svc.background_process_presence() as first, svc.background_process_presence() as second:
        assert (first, second) == (True, False)


def test_the_process_records_its_id_while_it_runs_and_removes_it_afterwards(private_state):
    with svc.background_process_presence():
        assert (private_state / svc.PRESENCE_PID_NAME).read_text() == str(os.getpid())
    assert not (private_state / svc.PRESENCE_PID_NAME).exists()


def test_install_turns_autostart_on_with_the_command_and_starts_the_process(registry, monkeypatch):
    calls, _ = fake_popen(monkeypatch)
    monkeypatch.setattr(sys, "executable", "C:\\Program Files\\Multazem\\.venv\\Scripts\\other.exe")
    ok, message = svc.service_install()
    assert (ok, message) == (True, "✓ Service installed and started")
    expected = subprocess.list2cmdline(svc.background_command())
    assert registry.value(RUN_KEY, "Multazem") == expected
    assert '"C:\\Program Files\\Multazem\\.venv\\Scripts\\other.exe"' in expected
    command, kwargs = calls[0]
    assert command == svc.background_command()
    assert kwargs["creationflags"] == 0x00000008 | 0x00000200
    assert kwargs["stdin"] == subprocess.DEVNULL


def test_install_does_not_start_a_second_process_when_one_runs(registry, monkeypatch):
    calls, _ = fake_popen(monkeypatch, claims_lock=False)
    with svc.background_process_presence():
        assert svc.service_install()[0] is True
    assert calls == []
    assert svc.service_is_enabled() is True


def test_install_turns_autostart_off_again_when_the_process_exits_at_once(registry, monkeypatch):
    fake_popen(monkeypatch, claims_lock=False, exit_code=1)
    ok, message = svc.service_install()
    assert ok is False
    assert message.startswith("Could not enable the service: the background process exited with code 1")
    assert svc.service_is_enabled() is False


def test_install_gives_up_when_the_process_never_claims_the_lock(registry, monkeypatch):
    fake_popen(monkeypatch, claims_lock=False)
    monkeypatch.setattr(svc, "START_TIMEOUT_SECONDS", 0.02)
    ok, message = svc.service_install()
    assert ok is False and "did not start within" in message
    assert svc.service_is_enabled() is False


def test_install_reports_a_process_that_cannot_be_started(registry, monkeypatch):
    def popen(*_args, **_kwargs):
        raise FileNotFoundError("pythonw.exe")

    monkeypatch.setattr(svc.subprocess, "Popen", popen)
    ok, message = svc.service_install()
    assert ok is False and "pythonw.exe" in message
    assert svc.service_is_enabled() is False


def test_install_reports_an_unwritable_registry_and_starts_nothing(registry, monkeypatch):
    calls, _ = fake_popen(monkeypatch)
    registry.write_error = PermissionError("denied")
    ok, message = svc.service_install()
    assert ok is False and message == "Could not write the service file: denied"
    assert calls == []


def test_uninstall_turns_autostart_off_and_ends_the_running_process(registry, monkeypatch):
    svc._write_run_value("x")
    killed = []
    presence = svc.background_process_presence()
    presence.__enter__()

    def kill(pid, sig):
        killed.append((pid, sig))
        presence.__exit__(None, None, None)

    monkeypatch.setattr(svc.os, "kill", kill)
    assert svc.service_uninstall() == (True, "✓ Service stopped and removed")
    assert killed == [(os.getpid(), signal.SIGTERM)]
    assert svc.service_is_enabled() is False and svc.service_is_active() is False


def test_uninstall_with_nothing_running_ends_no_process(registry, monkeypatch, private_state):
    svc._write_run_value("x")
    private_state.mkdir()
    (private_state / svc.PRESENCE_PID_NAME).write_text("4242")  # left behind by a process that crashed
    killed = []
    monkeypatch.setattr(svc.os, "kill", lambda pid, sig: killed.append(pid))
    assert svc.service_uninstall()[0] is True
    assert killed == []
    assert not (private_state / svc.PRESENCE_PID_NAME).exists()


def test_uninstall_works_when_autostart_was_never_on(registry):
    assert svc.service_uninstall() == (True, "✓ Service stopped and removed")


def test_uninstall_reports_an_unreadable_registry(registry, monkeypatch):
    def broken():
        raise PermissionError("denied")

    monkeypatch.setattr(svc, "_delete_run_value", broken)
    assert svc.service_uninstall() == (False, "Could not remove the service file: denied")


def test_a_stale_autostart_command_is_pointed_at_this_installation(registry):
    svc._write_run_value('"D:\\old\\pythonw.exe" -m multazem --headless')
    assert svc.refresh_autostart() is True
    assert registry.value(RUN_KEY, "Multazem") == subprocess.list2cmdline(svc.background_command())


def test_a_current_autostart_command_is_left_alone(registry):
    svc._write_run_value(subprocess.list2cmdline(svc.background_command()))
    assert svc.refresh_autostart() is False


def test_autostart_that_is_off_is_not_turned_on_by_the_refresh(registry):
    assert svc.refresh_autostart() is False
    assert svc.service_is_enabled() is False


def test_a_registry_error_during_the_refresh_is_logged_not_raised(registry, monkeypatch, capsys):
    registry.write_error = PermissionError("denied")
    monkeypatch.setattr(svc, "_read_run_value", lambda: "stale")
    assert svc.refresh_autostart() is False
    assert "Could not refresh the autostart command: denied" in capsys.readouterr().err
