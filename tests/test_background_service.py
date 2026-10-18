# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The platform facade of the background service: it hands every call to the module of the current system."""

import pytest

from multazem.services import background_service as facade


@pytest.mark.parametrize("name", ["service_is_enabled", "service_is_active", "service_install", "service_uninstall"])
@pytest.mark.parametrize("windows", [False, True])
def test_each_call_goes_to_the_module_of_the_platform(monkeypatch, name, windows):
    monkeypatch.setattr(facade, "is_windows", lambda: windows)
    monkeypatch.setattr(facade.systemd_service, name, lambda: "systemd")
    monkeypatch.setattr(facade.windows_service, name, lambda: "windows")
    assert getattr(facade, name)() == ("windows" if windows else "systemd")


def test_start_up_housekeeping_migrates_the_legacy_unit_on_linux(monkeypatch):
    monkeypatch.setattr(facade, "is_windows", lambda: False)
    monkeypatch.setattr(facade.systemd_service, "migrate_legacy_service", lambda: True)
    monkeypatch.setattr(facade.windows_service, "refresh_autostart", lambda: pytest.fail("Linux has no autostart"))
    assert facade.prepare_service() is True


def test_start_up_housekeeping_refreshes_the_autostart_command_on_windows(monkeypatch):
    monkeypatch.setattr(facade, "is_windows", lambda: True)
    monkeypatch.setattr(facade.windows_service, "refresh_autostart", lambda: True)
    monkeypatch.setattr(facade.systemd_service, "migrate_legacy_service", lambda: pytest.fail("no systemd here"))
    assert facade.prepare_service() is True


def test_off_windows_every_process_may_run_as_the_background_process(monkeypatch):
    monkeypatch.setattr(facade, "is_windows", lambda: False)
    with facade.register_background_process() as claimed:
        assert claimed is True


def test_on_windows_the_presence_of_the_service_module_is_used(monkeypatch):
    monkeypatch.setattr(facade, "is_windows", lambda: True)
    sentinel = object()
    monkeypatch.setattr(facade.windows_service, "background_process_presence", lambda: sentinel)
    assert facade.register_background_process() is sentinel
