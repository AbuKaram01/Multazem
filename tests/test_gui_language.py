# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Switching the language of the main window and the preferences, live and across restarts (GTK app under Xvfb)."""

import pytest

from gui_support import expected_rows, run_scenario, saved_settings

pytestmark = pytest.mark.gui


_LANGUAGE_SWITCH_SCRIPT = """
def snapshot(prefix):
    w = app._window
    d = w._pref_dialog
    out[prefix + "_title"] = w.get_title()
    out[prefix + "_dialog_title"] = d.get_title()
    out[prefix + "_rtl"] = Gtk.Widget.get_default_direction() == Gtk.TextDirection.RTL
    out[prefix + "_city"] = w._date_card.city_text
    out[prefix + "_hijri"] = w._date_card._hijri_label.get_text()
    out[prefix + "_countdown"] = w._next_card.countdown_text
    out[prefix + "_rows"] = [r.get_title() for r in find(w._prayer_list, Adw.ActionRow)]
    out[prefix + "_friday"] = w._schedule.today.date.weekday() == 4
    out[prefix + "_has_schedule"] = w._schedule is not None
    out[prefix + "_same_dialog"] = d is app._window._pref_dialog
def step1():
    d = open_preferences()
    out["start_language"] = app._settings.language
    one(d, Adw.ComboRow, "Language").set_selected(1)
    GLib.timeout_add(900, step2); return False
def step2():
    snapshot("ar")
    out["ar_saved"] = app._settings.language
    out["ar_language_row_selected"] = one(app._window._pref_dialog, Adw.ComboRow, "اللغة").get_selected()
    one(app._window._pref_dialog, Adw.ComboRow, "اللغة").set_selected(0)
    GLib.timeout_add(900, step3); return False
def step3():
    snapshot("en")
    out["en_saved"] = app._settings.language
    return finish()
GLib.timeout_add(1500, step1)
"""


def test_language_can_be_switched_live_from_the_preferences_and_back(tmp_path):
    out, err = run_scenario(tmp_path, _LANGUAGE_SWITCH_SCRIPT)
    assert "Traceback" not in err and out["start_language"] == "en"
    # Arabic
    assert out["ar_title"] == "Multazem" and out["ar_dialog_title"] == "الإعدادات" and out["ar_rtl"]
    assert out["ar_city"] == "📍 القاهرة" and out["ar_countdown"].startswith("باقي ")
    assert out["ar_rows"] == expected_rows("ar", out["ar_friday"])
    assert "AH" not in out["ar_hijri"] and out["ar_saved"] == "ar" and out["ar_language_row_selected"] == 1
    assert out["ar_has_schedule"] and out["ar_same_dialog"]
    # ... and back to English
    assert out["en_title"] == "Multazem" and out["en_dialog_title"] == "Preferences" and not out["en_rtl"]
    assert out["en_city"] == "📍 Cairo" and out["en_countdown"].startswith("Time left ")
    assert out["en_rows"] == expected_rows("en", out["en_friday"])
    assert out["en_hijri"].endswith("AH") and out["en_saved"] == "en" and out["en_has_schedule"]
    assert saved_settings(tmp_path)["language"] == "en"


def test_language_changed_in_the_settings_file_is_applied_while_running(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def step1():
            app._settings.language = "ar"
            GLib.timeout_add(900, step2); return False
        def step2():
            out["title"] = app._window.get_title()
            out["rtl"] = Gtk.Widget.get_default_direction() == Gtk.TextDirection.RTL
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    assert out == {"title": "Multazem", "rtl": True} and "Traceback" not in err


def test_the_chosen_language_is_remembered_across_restarts(tmp_path):
    _, err1 = run_scenario(
        tmp_path,
        """
        def step1():
            app._settings.language = "ar"
            GLib.timeout_add(600, finish); return False
        GLib.timeout_add(1500, step1)
    """,
    )
    second, err2 = run_scenario(
        tmp_path,
        """
        def check():
            out["title"] = app._window.get_title()
            return finish()
        GLib.timeout_add(1500, check)
    """,
    )
    assert second["title"] == "Multazem" and "Traceback" not in err1 + err2
