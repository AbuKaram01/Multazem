# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Where the files live on Windows, checked on any system by switching ``is_windows`` on."""

from pathlib import Path

import pytest

from multazem.services import paths


@pytest.fixture
def on_windows(monkeypatch):
    """Makes the path functions behave as on Windows."""
    monkeypatch.setattr(paths, "is_windows", lambda: True)


def test_settings_live_in_the_roaming_profile(on_windows, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert paths.config_home() == tmp_path / "roaming"
    assert paths.settings_file() == tmp_path / "roaming" / "multazem" / "settings.json"


def test_xdg_config_home_is_ignored_on_windows(on_windows, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert paths.config_home() == tmp_path / "roaming"


@pytest.mark.parametrize("value", ["", "relative/dir"])
def test_unusable_appdata_falls_back_to_the_profile_folder(on_windows, tmp_path, monkeypatch, value):
    monkeypatch.setenv("APPDATA", value)
    assert paths.config_home() == Path.home() / "AppData" / "Roaming"


def test_machine_files_live_in_local_app_data(on_windows, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert paths.local_data_dir() == tmp_path / "local" / "multazem"
    assert paths.log_file() == tmp_path / "local" / "multazem" / "multazem.log"


def test_unusable_local_app_data_falls_back_to_the_profile_folder(on_windows, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", "")
    assert paths.local_data_dir() == Path.home() / "AppData" / "Local" / "multazem"


def test_data_dir_follows_xdg_data_home_elsewhere(off_windows, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    assert paths.local_data_dir() == tmp_path / "share" / "multazem"


def test_data_dir_defaults_to_local_share_elsewhere(off_windows, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", "")
    assert paths.local_data_dir() == Path.home() / ".local" / "share" / "multazem"


def test_the_icon_is_found_in_the_project_and_has_the_ico_name():
    icon = paths.windows_icon_file()
    assert icon is not None and icon.name == "multazem.ico"


def test_the_icon_is_none_when_it_is_nowhere(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.Path, "is_file", lambda self: False)
    assert paths.windows_icon_file() is None
