# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Windows toast notifications: the PowerShell program, its encoding, the registration and the outcome reporting."""

import base64
import subprocess
from types import SimpleNamespace

import pytest

from multazem.services import notifications
from multazem.services import windows_toast as toast

from windows_support import install_fake_winreg


def decode(command):
    """Returns the PowerShell source that an ``-EncodedCommand`` command line carries."""
    return base64.b64decode(command[-1]).decode("utf-16-le")


def test_the_script_shows_a_toast_for_the_application_identity():
    script = toast.toast_script("Fajr", "It is 04:50")
    assert "CreateToastNotifier('com.github.multazem').Show($toast)" in script
    assert "<text>Fajr</text><text>It is 04:50</text>" in script


def test_xml_special_characters_in_the_text_are_escaped():
    script = toast.toast_script("A & B", "<b>1 < 2</b>")
    assert "<text>A &amp; B</text><text>&lt;b&gt;1 &lt; 2&lt;/b&gt;</text>" in script


def test_single_quotes_are_doubled_so_the_text_cannot_end_the_powershell_string():
    script = toast.toast_script("It's time", "x'); Remove-Item -Recurse C:\\ #")
    assert "It''s time" in script
    assert "x''); Remove-Item -Recurse C:\\ #" in script


def test_a_failure_is_reported_on_standard_error_with_exit_code_one():
    script = toast.toast_script("t", "b")
    assert script.index("catch") < script.index("[Console]::Error.WriteLine") < script.index("exit 1")


def test_the_command_line_carries_the_script_as_utf16_base64():
    script = toast.toast_script("حان وقت الفجر", "الساعة 04:50")
    command = toast.powershell_command(script)
    assert command[0] == "powershell.exe"
    assert command[command.index("-EncodedCommand") + 1] == command[-1]
    assert decode(command) == script
    assert "حان وقت الفجر" in decode(command)


def test_the_window_stays_hidden_and_no_profile_is_loaded():
    command = toast.powershell_command("x")
    assert command[1:5] == ["-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden"]


def test_registration_stores_the_name_and_the_icon_for_the_user(monkeypatch, tmp_path):
    registry = install_fake_winreg(monkeypatch)
    icon = tmp_path / "multazem.ico"
    monkeypatch.setattr(toast, "windows_icon_file", lambda: icon)
    toast.register_toast_app()
    key = r"Software\Classes\AppUserModelId\com.github.multazem"
    assert registry.value(key, "DisplayName") == "Multazem"
    assert registry.value(key, "IconUri") == str(icon)


def test_registration_without_an_icon_file_still_sets_the_name(monkeypatch):
    registry = install_fake_winreg(monkeypatch)
    monkeypatch.setattr(toast, "windows_icon_file", lambda: None)
    toast.register_toast_app()
    key = r"Software\Classes\AppUserModelId\com.github.multazem"
    assert registry.value(key, "DisplayName") == "Multazem"
    assert registry.value(key, "IconUri") is None


def fake_run(monkeypatch, result=None, error=None):
    """Replaces ``subprocess.run`` of the toast module; returns the list of recorded calls."""
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(toast.subprocess, "run", run)
    return calls


@pytest.fixture
def registered(monkeypatch):
    """A fake registry and no icon, so that sending a toast can get as far as starting PowerShell."""
    registry = install_fake_winreg(monkeypatch)
    monkeypatch.setattr(toast, "windows_icon_file", lambda: None)
    return registry


def test_a_toast_that_powershell_shows_succeeds(registered, monkeypatch):
    calls = fake_run(monkeypatch, SimpleNamespace(returncode=0, stderr=""))
    assert toast.send_toast("Dhuhr", "12:42") == (True, "")
    command, kwargs = calls[0]
    assert "Dhuhr" in decode(command)
    assert kwargs["timeout"] == toast.TOAST_TIMEOUT_SECONDS and kwargs["stdin"] == subprocess.DEVNULL


def test_the_powershell_window_is_suppressed(registered, monkeypatch):
    calls = fake_run(monkeypatch, SimpleNamespace(returncode=0, stderr=""))
    toast.send_toast("t", "b")
    assert calls[0][1]["creationflags"] == 0x08000000


def test_the_message_of_a_failed_toast_is_the_text_powershell_wrote(registered, monkeypatch):
    fake_run(monkeypatch, SimpleNamespace(returncode=1, stderr="Element not found.\r\n"))
    assert toast.send_toast("t", "b") == (False, "Element not found.")


def test_a_failed_toast_without_text_reports_the_exit_code(registered, monkeypatch):
    fake_run(monkeypatch, SimpleNamespace(returncode=3, stderr=""))
    assert toast.send_toast("t", "b") == (False, "powershell.exe exited with code 3")


def test_missing_powershell_is_reported(registered, monkeypatch):
    fake_run(monkeypatch, error=FileNotFoundError())
    assert toast.send_toast("t", "b") == (False, "powershell.exe was not found")


def test_a_hung_powershell_is_reported_after_the_timeout(registered, monkeypatch):
    fake_run(monkeypatch, error=subprocess.TimeoutExpired("powershell.exe", 30))
    ok, detail = toast.send_toast("t", "b")
    assert not ok and "30 seconds" in detail


def test_other_start_errors_are_reported(registered, monkeypatch):
    fake_run(monkeypatch, error=PermissionError("access denied"))
    assert toast.send_toast("t", "b") == (False, "access denied")


def test_an_unwritable_registry_is_reported_without_starting_powershell(registered, monkeypatch):
    registered.write_error = PermissionError("denied")
    calls = fake_run(monkeypatch, SimpleNamespace(returncode=0, stderr=""))
    ok, detail = toast.send_toast("t", "b")
    assert not ok and "could not be registered" in detail and "denied" in detail
    assert calls == []


def test_on_windows_the_notification_is_a_toast(monkeypatch):
    shown = []
    monkeypatch.setattr(notifications, "is_windows", lambda: True)
    monkeypatch.setattr(notifications, "send_toast", lambda title, body: shown.append((title, body)) or (True, ""))
    assert notifications.send_notification("Dhuhr prayer time", "It is 12:42", "weather-clear-symbolic") == (True, "")
    assert shown == [("Dhuhr prayer time", "It is 12:42")]


def test_on_windows_a_failed_toast_is_reported_and_logged(monkeypatch, capsys):
    monkeypatch.setattr(notifications, "is_windows", lambda: True)
    monkeypatch.setattr(notifications, "send_toast", lambda title, body: (False, "powershell.exe was not found"))
    assert notifications.send_notification("t", "b") == (False, "powershell.exe was not found")
    assert "powershell.exe was not found" in capsys.readouterr().err
