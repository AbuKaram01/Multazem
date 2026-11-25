# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The per-prayer notification bells of the main window, checked in the real application under Xvfb."""

import pytest

from gui_support import run_scenario, saved_settings

pytestmark = pytest.mark.gui


def test_bell_toggles_per_prayer_persist_and_look_right(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def step1():
            w = app._window
            bells = w._prayer_list.bells
            out["bell_names"] = sorted(p.value for p in bells)
            b = bells[Prayer.DHUHR]
            out["initial"] = [b.get_active(), b.get_icon_name()]
            b.set_active(False)
            out["after_off"] = [
                w._settings.prayer_enabled(Prayer.DHUHR), b.get_icon_name(), "off" in b.get_tooltip_text()]
            others = (Prayer.FAJR, Prayer.SUNRISE, Prayer.ASR, Prayer.MAGHRIB, Prayer.ISHA)
            out["others_untouched"] = all(w._settings.prayer_enabled(p) for p in others)
            b.set_active(True)
            out["after_on"] = [w._settings.prayer_enabled(Prayer.DHUHR), b.get_icon_name()]
            b.set_active(False)
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    assert out["bell_names"] == sorted(["fajr", "sunrise", "dhuhr", "asr", "maghrib", "isha"])
    assert out["initial"] == [True, "multazem-bell-symbolic"]
    assert out["after_off"] == [False, "multazem-bell-off-symbolic", True] and out["others_untouched"]
    assert out["after_on"] == [True, "multazem-bell-symbolic"] and "Traceback" not in err
    assert saved_settings(tmp_path)["notify_dhuhr"] is False


def test_sunrise_has_a_bell_that_behaves_exactly_like_the_prayers(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def step1():
            w = app._window
            lst = w._prayer_list
            bell = lst.bells[Prayer.SUNRISE]
            out["initial"] = [bell.get_active(), bell.get_icon_name(), bell.get_sensitive(), bell.get_tooltip_text()]
            out["same_css"] = bell.get_css_classes() == lst.bells[Prayer.FAJR].get_css_classes()
            bell.set_active(False)
            out["off"] = [w._settings.prayer_enabled(Prayer.SUNRISE), bell.get_icon_name(), bell.get_tooltip_text()]
            out["others_untouched"] = all(w._settings.prayer_enabled(p) for p in Prayer if p is not Prayer.SUNRISE)
            out["time_label_kept"] = lst.time_labels[Prayer.SUNRISE].get_text() != "--:--"
            w._settings.set_prayer_enabled(Prayer.SUNRISE, True)
            GLib.timeout_add(700, step2); return False
        def step2():
            bell = app._window._prayer_list.bells[Prayer.SUNRISE]
            out["resynced"] = [bell.get_active(), bell.get_icon_name()]
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    assert out["initial"] == [True, "multazem-bell-symbolic", True, "Sunrise notifications: on (click to turn off)"]
    assert out["same_css"] and out["time_label_kept"] and "Traceback" not in err
    assert out["off"] == [False, "multazem-bell-off-symbolic", "Sunrise notifications: off (click to turn on)"]
    assert out["others_untouched"] and out["resynced"] == [True, "multazem-bell-symbolic"]
    assert saved_settings(tmp_path)["notify_sunrise"] is True


def test_the_sunrise_choice_is_remembered_across_restarts(tmp_path):
    _, err1 = run_scenario(
        tmp_path,
        """
        def step1():
            app._window._prayer_list.bells[Prayer.SUNRISE].set_active(False)
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    second, err2 = run_scenario(
        tmp_path,
        """
        def step1():
            bell = app._window._prayer_list.bells[Prayer.SUNRISE]
            out["state"] = [bell.get_active(), bell.get_icon_name()]
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    assert "Traceback" not in err1 + err2
    assert second["state"] == [False, "multazem-bell-off-symbolic"]


_FRIDAY_SCENARIO = """
    from datetime import date, datetime
    from multazem.core.prayer_times import calculate_prayer_times
    CAIRO = (30.0444, 31.2357, "Africa/Cairo")
    def snapshot(prefix, day, now):
        w = app._window
        w._schedule.today = calculate_prayer_times(*CAIRO, day)
        w._update_ui()
        w._update_countdown(now)
        out[prefix + "_rows"] = [r.get_title() for r in find(w._prayer_list, Adw.ActionRow)]
        out[prefix + "_card"] = w._next_card.name_text
        out[prefix + "_bell"] = w._prayer_list.bells[Prayer.DHUHR].get_tooltip_text()
        out[prefix + "_switch"] = w._settings.prayer_enabled(Prayer.DHUHR)
    def step1():
        snapshot("friday", date(2026, 10, 9), datetime(2026, 10, 9, 10, 0))
        snapshot("saturday", date(2026, 10, 10), datetime(2026, 10, 10, 10, 0))
        snapshot("friday_again", date(2026, 10, 9), datetime(2026, 10, 9, 10, 0))
        w = app._window
        w._prayer_list.bells[Prayer.DHUHR].set_active(False)
        snapshot("saturday_after", date(2026, 10, 10), datetime(2026, 10, 10, 10, 0))
        out["muted_everyday"] = not w._settings.prayer_enabled(Prayer.DHUHR)
        return finish()
    GLib.timeout_add(1800, step1)
"""


def test_the_dhuhr_slot_is_shown_as_jumuah_on_fridays_in_english(tmp_path):
    out, err = run_scenario(tmp_path, _FRIDAY_SCENARIO)
    assert "Traceback" not in err
    assert out["friday_rows"] == ["Fajr", "Sunrise", "Jumu'ah", "Asr", "Maghrib", "Isha"]
    assert out["friday_card"] == "Jumu'ah"
    assert out["friday_bell"] == "Jumu'ah notifications: on (click to turn off)"
    assert out["saturday_rows"] == ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
    assert out["saturday_card"] == "Dhuhr" and out["saturday_bell"].startswith("Dhuhr notifications")
    assert out["friday_again_rows"][2] == "Jumu'ah"
    assert out["saturday_after_rows"][2] == "Dhuhr" and out["muted_everyday"]
    assert "off" in out["saturday_after_bell"]


def test_the_dhuhr_slot_is_shown_as_aljumuah_on_fridays_in_arabic(tmp_path):
    out, err = run_scenario(tmp_path, _FRIDAY_SCENARIO, settings={"language": "ar"})
    assert "Traceback" not in err
    assert out["friday_rows"] == ["الفجر", "الشروق", "الجمعة", "العصر", "المغرب", "العشاء"]
    assert out["friday_card"] == "الجمعة"
    assert out["friday_bell"] == "إشعارات الجمعة: مفعّلة (اضغط للإيقاف)"
    assert out["saturday_rows"][2] == "الظهر" and out["saturday_card"] == "الظهر"


def test_the_jumuah_name_survives_a_language_switch_on_a_friday(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        from datetime import date, datetime
        from multazem.core.prayer_times import calculate_prayer_times
        def step1():
            w = app._window
            w._schedule.today = calculate_prayer_times(30.0444, 31.2357, "Africa/Cairo", date(2026, 10, 9))
            w._update_ui()
            out["en"] = w._prayer_list.rows[Prayer.DHUHR].get_title()
            app._settings.language = "ar"
            GLib.timeout_add(900, step2); return False
        def step2():
            w = app._window
            # The rebuilt window recalculates from the real clock, so force a Friday again.
            w._schedule.today = calculate_prayer_times(30.0444, 31.2357, "Africa/Cairo", date(2026, 10, 9))
            w._update_ui()
            out["ar"] = w._prayer_list.rows[Prayer.DHUHR].get_title()
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    assert "Traceback" not in err and out["en"] == "Jumu'ah" and out["ar"] == "الجمعة"


def test_bells_follow_settings_changed_elsewhere_and_dim_when_notifications_are_off(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def step1():
            w = app._window
            w._settings.set_prayer_enabled(Prayer.ASR, False)
            GLib.timeout_add(700, step2); return False
        def step2():
            w = app._window
            bell = w._prayer_list.bells[Prayer.ASR]
            out["bell_synced"] = [bell.get_active(), bell.get_icon_name()]
            w._settings.notify_on_prayer = False
            w._settings.reminder_enabled = False
            GLib.timeout_add(700, step3); return False
        def step3():
            w = app._window
            out["dimmed"] = not w._prayer_list.bells[Prayer.FAJR].get_sensitive()
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    assert out["bell_synced"] == [False, "multazem-bell-off-symbolic"] and out["dimmed"] and "Traceback" not in err
