# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


import pytest

from gui_support import run_scenario

pytestmark = pytest.mark.gui


def test_ui_updates_live_when_the_location_changes_without_closing_anything(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def step1():
            w = app._window
            out["before"] = [w._date_card.city_text, w._prayer_list.time_labels[Prayer.DHUHR].get_text()]
            st = w._settings
            st.city_name = "Aswan"; st.latitude = 24.0889; st.longitude = 32.8998
            GLib.timeout_add(900, step2); return False
        def step2():
            w = app._window
            out["after"] = [w._date_card.city_text, w._prayer_list.time_labels[Prayer.DHUHR].get_text()]
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    assert "Cairo" in out["before"][0] and "Aswan" in out["after"][0]
    assert out["before"][1] != out["after"][1] and "Traceback" not in err


_PREFERENCES_FLOW_SCRIPT = """
from multazem.ui.preferences.compare_dialog import show_method_comparison
def step1():
    win = app._window
    d1 = open_preferences()
    win.lookup_action("preferences").activate(None)
    out["single_instance"] = win._pref_dialog is d1
    st = win._settings
    picker = one(d1, Adw.ComboRow, "Quick pick a region")
    picker.set_selected(10)
    out["city"] = st.city_name
    out["picked_name_matches_list"] = out["city"] == model_strings(picker)[10]
    tz = one(d1, Adw.EntryRow, "Time zone")
    tz.set_text("Foo/Bar"); out["bad_tz_kept_old"] = st.timezone_name == "Africa/Cairo"
    out["bad_tz_flagged"] = tz.has_css_class("error")
    tz.set_text("Asia/Riyadh"); out["good_tz_saved"] = st.timezone_name == "Asia/Riyadh"
    out["good_tz_unflagged"] = not tz.has_css_class("error")
    one(d1, Adw.ComboRow, "Asr calculation").set_selected(1)
    out["asr_shadow"] = st.asr_shadow
    one(d1, Adw.ComboRow, "Method").set_selected(3); out["method"] = st.calculation_method.name
    one(d1, Adw.SpinRow, "Reminder lead time").set_value(25); out["mins"] = st.reminder_minutes
    show_method_comparison(d1, st)
    d1.close()
    GLib.timeout_add(600, step2)
    return False
def step2():
    w = app._window
    out["dialog_cleared"] = w._pref_dialog is None
    out["still_has_schedule"] = w._schedule is not None
    # The main screen must reflect the new settings after closing (the original bug: it did not).
    out["header_city_updated"] = out["city"] in w._date_card.city_text
    from multazem.core.prayer_times import calculate_prayer_times
    st = w._settings
    expected = calculate_prayer_times(st.latitude, st.longitude, "Asia/Riyadh", None, st.calculation_method, 2)
    out["times_follow_settings"] = (
        w._schedule.today.asr == expected.asr and w._schedule.tz_name == "Asia/Riyadh")
    w.lookup_action("preferences").activate(None)
    out["reopens"] = w._pref_dialog is not None
    return finish()
GLib.timeout_add(1500, step1)
"""


def test_preferences_flow_and_single_instance(tmp_path):
    out, err = run_scenario(tmp_path, _PREFERENCES_FLOW_SCRIPT)
    assert out["single_instance"] and out["picked_name_matches_list"]
    assert out["bad_tz_kept_old"] and out["bad_tz_flagged"] and out["good_tz_saved"] and out["good_tz_unflagged"]
    assert out["asr_shadow"] == 2 and out["method"] == "UMM_AL_QURA" and out["mins"] == 25
    assert out["dialog_cleared"] and out["still_has_schedule"]
    assert out["times_follow_settings"] and out["reopens"] and out["header_city_updated"]
    assert "Traceback" not in err


def test_preferences_dialog_is_built_in_the_active_language(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def check():
            d = open_preferences()
            out["title"] = d.get_title()
            out["groups"] = [g.get_title() for g in find(d, Adw.PreferencesGroup)]
            out["methods"] = model_strings(one(d, Adw.ComboRow, "الطريقة"))[:2]
            out["languages"] = model_strings(one(d, Adw.ComboRow, "اللغة"))
            out["language_selected"] = one(d, Adw.ComboRow, "اللغة").get_selected()
            out["add_title"] = one(d, AddRegionRow).get_title()
            return finish()
        GLib.timeout_add(2000, check)
    """,
        settings={"language": "ar"},
    )
    assert out["title"] == "الإعدادات"
    assert out["groups"] == ["الموقع الجغرافي", "طريقة حساب أوقات الصلاة", "إعدادات الإشعارات", "خيارات العرض"]
    assert out["methods"] == ["الهيئة المصرية", "رابطة العالم الإسلامي"]
    assert out["languages"] == ["English", "العربية"]
    assert out["language_selected"] == 1 and out["add_title"] == "إضافة منطقة" and "Traceback" not in err
