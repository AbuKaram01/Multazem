# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Migration from the former application name (``salah-reminder``): configuration files and the systemd unit."""

import json
import subprocess
import sys
import time

import pytest
from test_cli import env_for

from multazem.core.prayers import Prayer
from multazem.services import legacy_config
from multazem.services import systemd_service as svc
from multazem.services.paths import config_dir, legacy_config_dir
from multazem.services.region_catalog import RegionCatalog
from multazem.services.settings import Settings

OLD_SETTINGS = {"city_name": "Aswan", "language": "ar", "reminder_minutes": 25, "notify_fajr": False}
OLD_REGIONS = {
    "version": 1,
    "regions": [{"name": "My Farm", "latitude": 30.5, "longitude": 31.1, "timezone": "Africa/Cairo"}],
}


def write_legacy(settings=None, regions=None):
    """Creates the former configuration directory with the given settings and regions files; returns it."""
    legacy = legacy_config_dir()
    legacy.mkdir(parents=True)
    if settings is not None:
        (legacy / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    if regions is not None:
        (legacy / "regions.json").write_text(json.dumps(regions), encoding="utf-8")
    return legacy


def test_directory_names():
    assert config_dir().name == "multazem" and legacy_config_dir().name == "salah-reminder"
    assert config_dir().parent == legacy_config_dir().parent


def test_settings_and_regions_are_copied_to_the_new_directory():
    legacy = write_legacy(OLD_SETTINGS, OLD_REGIONS)
    assert legacy_config.migrate_legacy_config() == ["settings.json", "regions.json"]
    assert json.loads((config_dir() / "settings.json").read_text(encoding="utf-8")) == OLD_SETTINGS
    assert json.loads((config_dir() / "regions.json").read_text(encoding="utf-8")) == OLD_REGIONS
    assert (legacy / "settings.json").exists() and (legacy / "regions.json").exists()


def test_the_migrated_files_are_what_the_application_then_loads():
    write_legacy(OLD_SETTINGS, OLD_REGIONS)
    legacy_config.migrate_legacy_config()
    settings = Settings()
    assert settings.city_name == "Aswan" and settings.language == "ar" and settings.reminder_minutes == 25
    assert settings.prayer_enabled(Prayer.FAJR) is False
    assert [r.name("en") for r in RegionCatalog().custom_regions] == ["My Farm"]


def test_nothing_is_overwritten_once_the_new_version_has_its_own_files():
    write_legacy(OLD_SETTINGS, OLD_REGIONS)
    config_dir().mkdir(parents=True)
    (config_dir() / "settings.json").write_text('{"city_name": "Tanta"}', encoding="utf-8")
    assert legacy_config.migrate_legacy_config() == ["regions.json"]
    assert json.loads((config_dir() / "settings.json").read_text(encoding="utf-8")) == {"city_name": "Tanta"}


def test_running_it_twice_changes_nothing():
    write_legacy(OLD_SETTINGS)
    assert legacy_config.migrate_legacy_config() == ["settings.json"]
    (config_dir() / "settings.json").write_text('{"city_name": "Luxor"}', encoding="utf-8")
    assert legacy_config.migrate_legacy_config() == []
    assert json.loads((config_dir() / "settings.json").read_text(encoding="utf-8")) == {"city_name": "Luxor"}


def test_a_fresh_install_has_nothing_to_migrate():
    assert legacy_config.migrate_legacy_config() == []
    assert not config_dir().exists()


def test_other_files_in_the_old_directory_are_left_alone():
    legacy = write_legacy(OLD_SETTINGS)
    (legacy / "settings.json.corrupt").write_text("junk", encoding="utf-8")
    legacy_config.migrate_legacy_config()
    assert sorted(p.name for p in config_dir().iterdir()) == ["settings.json"]


def test_a_copy_failure_is_reported_and_never_raised(monkeypatch, capsys):
    write_legacy(OLD_SETTINGS)

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(legacy_config.shutil, "copy2", boom)
    assert legacy_config.migrate_legacy_config() == []
    assert "disk full" in capsys.readouterr().err
    assert not list(config_dir().glob("*.migrating")) and not (config_dir() / "settings.json").exists()


def test_the_headless_service_migrates_too(tmp_path):
    """The background service may be the first thing the new version runs."""
    legacy = tmp_path / "cfg" / "salah-reminder"
    legacy.mkdir(parents=True)
    (legacy / "settings.json").write_text(json.dumps({"city_name": "Aswan"}), encoding="utf-8")
    p = subprocess.Popen(
        [sys.executable, "-m", "multazem", "--headless"],
        env=env_for(tmp_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(1.5)
    p.terminate()
    out, err = p.communicate(timeout=10)
    assert "Traceback" not in err and "[migration] Copied settings.json" in out
    migrated = tmp_path / "cfg" / "multazem" / "settings.json"
    assert json.loads(migrated.read_text(encoding="utf-8"))["city_name"] == "Aswan"


def fake_systemctl(monkeypatch, enabled_units=()):
    """Replaces ``systemctl`` by a recorder that reports only ``enabled_units`` as enabled; returns its calls."""
    calls = []

    def run(*args, timeout=10):
        calls.append(args)
        if args[0] == "is-enabled":
            return (args[1] in enabled_units), ("enabled" if args[1] in enabled_units else "disabled")
        return True, ""

    monkeypatch.setattr(svc, "_run_systemctl", run)
    return calls


def lay_out_units(monkeypatch, tmp_path, legacy=True):
    """Points the service module at a temporary unit directory, with a legacy unit file in it by default."""
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    monkeypatch.setattr(svc, "_SERVICE_DIR", unit_dir)
    monkeypatch.setattr(svc, "_SERVICE_PATH", unit_dir / svc.SERVICE_NAME)
    if legacy:
        (unit_dir / "salah-reminder.service").write_text("[Service]\nExecStart=/usr/bin/salah-reminder\n")
    return unit_dir


@pytest.mark.skipif(sys.platform == "win32", reason="systemd exists only on Linux")
def test_unit_names():
    assert svc.SERVICE_NAME == "multazem.service" and svc.LEGACY_SERVICE_NAME == "salah-reminder.service"


@pytest.mark.skipif(sys.platform == "win32", reason="systemd exists only on Linux")
def test_an_enabled_legacy_service_is_removed_and_replaced_by_the_new_one(monkeypatch, tmp_path):
    unit_dir = lay_out_units(monkeypatch, tmp_path)
    calls = fake_systemctl(monkeypatch, enabled_units={"salah-reminder.service"})
    assert svc.migrate_legacy_service() is True
    assert not (unit_dir / "salah-reminder.service").exists()
    assert ("disable", "--now", "salah-reminder.service") in calls
    assert ("enable", "--now", "multazem.service") in calls
    assert (unit_dir / "multazem.service").exists()
    assert (
        "multazem" in (unit_dir / "multazem.service").read_text()
        and "salah" not in (unit_dir / "multazem.service").read_text()
    )


@pytest.mark.skipif(sys.platform == "win32", reason="systemd exists only on Linux")
def test_a_disabled_legacy_service_is_only_removed(monkeypatch, tmp_path):
    unit_dir = lay_out_units(monkeypatch, tmp_path)
    calls = fake_systemctl(monkeypatch)
    assert svc.migrate_legacy_service() is True
    assert not (unit_dir / "salah-reminder.service").exists() and not (unit_dir / "multazem.service").exists()
    assert not any(c[0] == "enable" for c in calls)


@pytest.mark.skipif(sys.platform == "win32", reason="systemd exists only on Linux")
def test_without_a_legacy_unit_systemctl_is_never_called(monkeypatch, tmp_path):
    lay_out_units(monkeypatch, tmp_path, legacy=False)
    calls = fake_systemctl(monkeypatch)
    assert svc.migrate_legacy_service() is False and calls == []


@pytest.mark.skipif(sys.platform == "win32", reason="systemd exists only on Linux")
def test_an_already_enabled_new_service_is_not_installed_twice(monkeypatch, tmp_path):
    lay_out_units(monkeypatch, tmp_path)
    calls = fake_systemctl(monkeypatch, enabled_units={"salah-reminder.service", "multazem.service"})
    svc.migrate_legacy_service()
    assert not any(c[0] == "enable" for c in calls)


@pytest.mark.skipif(sys.platform == "win32", reason="systemd exists only on Linux")
def test_a_failing_install_is_reported_not_raised(monkeypatch, tmp_path, capsys):
    lay_out_units(monkeypatch, tmp_path)

    def run(*args, timeout=10):
        if args[0] == "is-enabled":
            return args[1] == "salah-reminder.service", "enabled"
        return (args[0] != "enable"), "boom"

    monkeypatch.setattr(svc, "_run_systemctl", run)
    assert svc.migrate_legacy_service() is True
    assert "[migration] Background service:" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform == "win32", reason="systemd exists only on Linux")
def test_an_unremovable_legacy_unit_is_reported(monkeypatch, tmp_path, capsys):
    unit_dir = lay_out_units(monkeypatch, tmp_path)
    fake_systemctl(monkeypatch)
    real_unlink = type(unit_dir).unlink

    def deny(self, missing_ok=False):
        if self.name == "salah-reminder.service":
            raise PermissionError(13, "denied")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(type(unit_dir), "unlink", deny)
    assert svc.migrate_legacy_service() is False
    assert "Could not remove" in capsys.readouterr().err
