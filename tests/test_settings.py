# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Settings: defaults, validation of saved values, persistence, change detection and listeners."""

import json
import os
import sys
import threading
from pathlib import Path

import pytest

from multazem.core.calculation import CalculationMethod
from multazem.core.prayer_times import CalculationParams
from multazem.core.prayers import Prayer
from multazem.services import paths
from multazem.services.paths import config_home
from multazem.services.settings import DEFAULTS, PRAYER_NOTIFY_KEYS, Settings


def write(path: Path, content, mode="w"):
    """Writes ``content`` to ``path``, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode) as handle:
        handle.write(content)


def test_first_run_creates_defaults(settings_path):
    s = Settings(settings_path)
    assert json.loads(settings_path.read_text(encoding="utf-8")) == DEFAULTS
    assert s.city_name == "Cairo" and s.calculation_method is CalculationMethod.EGYPTIAN


def test_roundtrip_persistence(settings_path):
    s = Settings(settings_path)
    s.city_name = "الإسكندرية"
    s.reminder_minutes = 25
    s.calculation_method = CalculationMethod.UMM_AL_QURA
    reloaded = Settings(settings_path)
    assert (reloaded.city_name, reloaded.reminder_minutes, reloaded.calculation_method) == (
        "الإسكندرية",
        25,
        CalculationMethod.UMM_AL_QURA,
    )


def test_calculation_params_bundle_the_location_and_method(settings):
    settings.calculation_method = CalculationMethod.KUWAIT
    settings.asr_shadow = 2
    assert settings.calculation_params == CalculationParams(
        latitude=DEFAULTS["latitude"],
        longitude=DEFAULTS["longitude"],
        timezone="Africa/Cairo",
        method=CalculationMethod.KUWAIT,
        asr_shadow=2,
    )


def test_english_is_the_default_language(settings_path):
    assert DEFAULTS["language"] == "en"
    assert Settings(settings_path).language == "en"


def test_language_persists_and_triggers_listeners(settings_path):
    s = Settings(settings_path)
    seen = []
    s.add_listener(seen.append)
    s.language = "ar"
    assert seen == ["language"]
    assert Settings(settings_path).language == "ar"


@pytest.mark.parametrize("bad", ["fr", "", "AR", 5, None, ["ar"]])
def test_unsupported_language_falls_back_to_english(settings_path, bad):
    write(settings_path, json.dumps({"language": bad, "city_name": "Aswan"}))
    s = Settings(settings_path)
    assert s.language == "en" and s.city_name == "Aswan"


def test_settings_file_from_before_the_language_option_opens_in_english(settings_path):
    write(settings_path, json.dumps({"city_name": "القاهرة", "reminder_minutes": 15}))
    s = Settings(settings_path)
    assert s.language == "en" and s.reminder_minutes == 15 and s.city_name == "القاهرة"


@pytest.mark.parametrize("value", ["", "relative/path", "./x", "~/cfg"])
def test_xdg_config_home_empty_or_relative_is_ignored(off_windows, monkeypatch, tmp_path, value):
    monkeypatch.setenv("HOME", str(tmp_path / "h"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "h"))  # where Path.home() looks on Windows
    monkeypatch.setenv("XDG_CONFIG_HOME", value)
    assert config_home() == tmp_path / "h" / ".config"


def test_xdg_config_home_absolute_is_honoured(off_windows, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom"))
    assert config_home() == tmp_path / "custom"


def test_default_files_follow_xdg(off_windows, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom"))
    assert paths.config_dir() == tmp_path / "custom" / "multazem"
    assert paths.settings_file().name == "settings.json"
    assert paths.custom_regions_file().name == "regions.json"
    assert paths.settings_file().parent == paths.custom_regions_file().parent


def test_settings_default_to_the_xdg_file(off_windows, monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "custom"))
    Settings()
    assert (tmp_path / "custom" / "multazem" / "settings.json").exists()


def test_config_dir_cannot_be_created_does_not_crash(tmp_path, capsys):
    (tmp_path / "blocker").write_text("x")
    s = Settings(tmp_path / "blocker" / "settings.json")
    s.city_name = "Aswan"
    assert s.city_name == "Aswan"
    assert "[settings]" in capsys.readouterr().err


@pytest.mark.parametrize(
    "content",
    ['{"latitude": 30.0, "city_name": "x",', "", "not json at all", "[1, 2, 3]", "null", '"string"', "42"],
)
def test_corrupt_file_resets_but_keeps_a_backup(settings_path, content, capsys):
    write(settings_path, content)
    s = Settings(settings_path)
    assert s.city_name == "Cairo"
    backup = settings_path.with_name("settings.json.corrupt")
    assert backup.read_text() == content
    assert json.loads(settings_path.read_text(encoding="utf-8")) == DEFAULTS
    assert "corrupt" in capsys.readouterr().err


def test_invalid_utf8_is_handled_as_corrupt(settings_path):
    write(settings_path, b"\xff\xfe\x00garbage\xc3\x28", mode="wb")
    s = Settings(settings_path)
    assert s.city_name == "Cairo"


def test_one_bad_value_does_not_throw_away_the_rest(settings_path):
    write(
        settings_path,
        json.dumps({"city_name": "Luxor", "reminder_minutes": 20, "latitude": "not a number", "play_adhan": "yes"}),
    )
    s = Settings(settings_path)
    assert s.city_name == "Luxor" and s.reminder_minutes == 20
    assert s.latitude == DEFAULTS["latitude"] and s.play_adhan is False


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "1e999", str(10**400), "true", '"31"', "null", "[]"])
def test_non_finite_or_wrong_type_numbers_fall_back(settings_path, raw):
    write(settings_path, '{"latitude": %s, "longitude": %s, "reminder_minutes": %s, "asr_shadow": %s}' % ((raw,) * 4))
    s = Settings(settings_path)
    assert s.latitude == DEFAULTS["latitude"]
    assert s.longitude == DEFAULTS["longitude"]
    assert s.reminder_minutes == DEFAULTS["reminder_minutes"]
    assert s.asr_shadow == 1


@pytest.mark.parametrize("tz", ["", "   ", "Foo/Bar", "../../etc/passwd", "/etc/passwd", 5, None])
def test_invalid_timezone_falls_back(settings_path, tz):
    write(settings_path, json.dumps({"timezone_name": tz}))
    assert Settings(settings_path).timezone_name == "Africa/Cairo"


def test_out_of_range_values_are_clamped(settings_path):
    write(settings_path, json.dumps({"latitude": 500, "longitude": -999, "reminder_minutes": 0, "asr_shadow": 7}))
    s = Settings(settings_path)
    assert (s.latitude, s.longitude, s.reminder_minutes, s.asr_shadow) == (90.0, -180.0, 1, 1)
    write(settings_path, json.dumps({"reminder_minutes": 10**6}))
    assert Settings(settings_path).reminder_minutes == 1440


def test_unknown_calculation_method_falls_back(settings_path):
    write(settings_path, json.dumps({"calculation_method": "MOONSIGHTING"}))
    assert Settings(settings_path).calculation_method is CalculationMethod.EGYPTIAN


def test_unreadable_file_is_not_overwritten(settings_path, monkeypatch):
    write(settings_path, json.dumps({"city_name": "Aswan"}))
    before = settings_path.read_bytes()
    real = Path.read_bytes

    def boom(self):
        if self == settings_path:
            raise PermissionError(13, "denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", boom)
    s = Settings(settings_path)
    assert s.city_name == "Cairo"
    monkeypatch.undo()
    assert settings_path.read_bytes() == before


def test_save_is_atomic_and_leaves_no_temp_files(settings_path, monkeypatch):
    s = Settings(settings_path)
    s.city_name = "Qena"
    original = settings_path.read_bytes()

    def failing_replace(src, dst):
        raise OSError("disk exploded")

    monkeypatch.setattr(os, "replace", failing_replace)
    s.city_name = "Sohag"
    monkeypatch.undo()
    assert settings_path.read_bytes() == original
    assert [p.name for p in settings_path.parent.iterdir()] == ["settings.json"]


def test_setting_the_same_value_does_not_touch_the_disk(settings_path):
    s = Settings(settings_path)
    s.city_name = "Tanta"
    stamp = settings_path.stat().st_mtime_ns
    s.city_name = "Tanta"
    s.reminder_minutes = DEFAULTS["reminder_minutes"]
    assert settings_path.stat().st_mtime_ns == stamp


def test_reload_detects_external_change_but_not_own_saves(settings_path):
    gui, service = Settings(settings_path), Settings(settings_path)
    assert service.reload_if_changed() is False
    gui.city_name = "Mansoura"
    gui.latitude = 31.04
    assert gui.reload_if_changed() is False
    assert service.reload_if_changed() is True
    assert (service.city_name, service.latitude) == ("Mansoura", 31.04)
    assert service.reload_if_changed() is False


def test_reload_keeps_memory_when_external_file_becomes_corrupt_or_vanishes(settings_path, capsys):
    s = Settings(settings_path)
    s.city_name = "Damietta"
    write(settings_path, "{broken")
    assert s.reload_if_changed() is False
    assert s.city_name == "Damietta"
    assert capsys.readouterr().err.count("unreadable") == 1
    assert s.reload_if_changed() is False
    settings_path.unlink()
    assert s.reload_if_changed() is False and s.city_name == "Damietta"


def test_concurrent_reader_never_sees_a_torn_file(settings_path):
    writer = Settings(settings_path)
    stop, errors = threading.Event(), []
    # On Windows a reader that arrives in the instant of the swap can be refused for a moment. That is not a torn
    # file, which is what this test is about (the writer retries the swap, see the atomic_json tests).
    refused_for_a_moment = PermissionError if sys.platform == "win32" else ()

    def write_loop():
        i = 0
        while not stop.is_set():
            writer.city_name = f"City {i}" + "ا" * (i % 500)
            i += 1

    thread = threading.Thread(target=write_loop)
    thread.start()
    try:
        for _ in range(1500):
            try:
                json.loads(settings_path.read_bytes())
            except refused_for_a_moment:
                continue
            except (ValueError, FileNotFoundError) as error:
                errors.append(error)
    finally:
        stop.set()
        thread.join()
    assert errors == []


def test_per_prayer_switches_default_to_on_and_roundtrip(settings_path):
    s = Settings(settings_path)
    assert set(PRAYER_NOTIFY_KEYS) == set(Prayer)
    assert all(s.prayer_enabled(prayer) for prayer in PRAYER_NOTIFY_KEYS)
    s.set_prayer_enabled(Prayer.DHUHR, False)
    reloaded = Settings(settings_path)
    assert reloaded.prayer_enabled(Prayer.DHUHR) is False and reloaded.prayer_enabled(Prayer.FAJR) is True


def test_sunrise_has_a_notification_switch_like_the_prayers(settings_path):
    s = Settings(settings_path)
    assert PRAYER_NOTIFY_KEYS[Prayer.SUNRISE] == "notify_sunrise" and DEFAULTS["notify_sunrise"] is True
    assert s.prayer_enabled(Prayer.SUNRISE) is True
    s.set_prayer_enabled(Prayer.SUNRISE, False)
    assert json.loads(settings_path.read_text(encoding="utf-8"))["notify_sunrise"] is False
    reloaded = Settings(settings_path)
    assert reloaded.prayer_enabled(Prayer.SUNRISE) is False
    assert all(reloaded.prayer_enabled(p) for p in Prayer if p is not Prayer.SUNRISE)


def test_settings_file_from_before_the_sunrise_switch_gets_it_on(settings_path):
    write(settings_path, json.dumps({"notify_fajr": False, "notify_dhuhr": True}))
    s = Settings(settings_path)
    assert s.prayer_enabled(Prayer.SUNRISE) is True and s.prayer_enabled(Prayer.FAJR) is False


@pytest.mark.parametrize("bad", ['"no"', "0", "null", "[]"])
def test_non_boolean_sunrise_value_falls_back_to_on(settings_path, bad):
    write(settings_path, f'{{"notify_sunrise": {bad}}}')
    assert Settings(settings_path).prayer_enabled(Prayer.SUNRISE) is True


def test_old_settings_file_without_the_new_keys_keeps_everything_on(settings_path):
    write(settings_path, json.dumps({"city_name": "Aswan", "notify_on_prayer": True}))
    s = Settings(settings_path)
    assert s.city_name == "Aswan" and s.prayer_enabled(Prayer.ASR) is True


@pytest.mark.parametrize("bad", ['"no"', "0", "null", "[]", "1"])
def test_non_boolean_per_prayer_value_falls_back_to_on(settings_path, bad):
    write(settings_path, f'{{"notify_asr": {bad}}}')
    assert Settings(settings_path).prayer_enabled(Prayer.ASR) is True


def test_listeners_fire_only_on_real_changes(settings):
    seen = []
    settings.add_listener(seen.append)
    settings.city_name = "Tanta"
    settings.city_name = "Tanta"
    settings.set_prayer_enabled(Prayer.FAJR, False)
    assert seen == ["city_name", "notify_fajr"]


def test_listener_gets_wildcard_for_external_change_and_a_broken_listener_is_harmless(settings_path, capsys):
    a, b = Settings(settings_path), Settings(settings_path)
    seen = []
    a.add_listener(lambda key: (_ for _ in ()).throw(RuntimeError("bad listener")))
    a.add_listener(seen.append)
    b.city_name = "Mansoura"
    assert a.reload_if_changed() is True and seen == ["*"]
    a.city_name = "Damietta"
    assert Settings(settings_path).city_name == "Damietta" and seen[-1] == "city_name"
    assert "listener" in capsys.readouterr().err
