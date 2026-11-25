# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The main window: layout, direction, city names, polar locations and icons (real GTK app under Xvfb)."""

import pytest

from gui_support import expected_rows, run_scenario

pytestmark = pytest.mark.gui


def test_window_opens_in_english_with_defaults_without_tracebacks(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def check():
            w = app._window
            out["has_window"] = w is not None
            out["schedule_ok"] = w._schedule is not None
            out["resizable"] = w.get_resizable()
            out["default_height"] = w.get_default_size()[1]
            out["leader_engine_started"] = app._scheduler._running
            out["title"] = w.get_title()
            out["city"] = w._date_card.city_text
            out["ltr"] = Gtk.Widget.get_default_direction() == Gtk.TextDirection.LTR
            out["hijri"] = w._date_card._hijri_label.get_text()
            out["next_name"] = w._next_card.name_text
            out["countdown"] = w._next_card.countdown_text
            out["rows"] = [r.get_title() for r in find(w._prayer_list, Adw.ActionRow)]
            out["friday"] = w._schedule.today.date.weekday() == 4
            return finish()
        GLib.timeout_add(2500, check)
    """,
    )
    assert out["has_window"] and out["schedule_ok"] and out["resizable"] and out["default_height"] <= 700
    assert out["leader_engine_started"] and "Traceback" not in err
    assert out["title"] == "Multazem" and out["city"] == "📍 Cairo" and out["ltr"]
    assert out["hijri"].endswith("AH") and out["countdown"].startswith("Time left ")
    assert out["next_name"] in {"Fajr", "Dhuhr", "Jumu'ah", "Asr", "Maghrib", "Isha"}
    assert out["rows"] == expected_rows("en", out["friday"])


def test_arabic_settings_open_a_right_to_left_arabic_window(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def check():
            w = app._window
            out["title"] = w.get_title()
            out["rtl"] = Gtk.Widget.get_default_direction() == Gtk.TextDirection.RTL
            out["card_rtl"] = w._date_card.get_direction() == Gtk.TextDirection.RTL
            out["city"] = w._date_card.city_text
            out["hijri"] = w._date_card._hijri_label.get_text()
            out["countdown"] = w._next_card.countdown_text
            out["rows"] = [r.get_title() for r in find(w._prayer_list, Adw.ActionRow)]
            out["weekday_ok"] = any(
                w._date_card.date_text.startswith(tr(f"weekday.{i}")) for i in range(7))
            out["friday"] = w._schedule.today.date.weekday() == 4
            return finish()
        GLib.timeout_add(2500, check)
    """,
        settings={"language": "ar"},
    )
    assert "Traceback" not in err
    assert out["title"] == "Multazem" and out["rtl"] and out["card_rtl"]
    assert out["city"] == "📍 القاهرة"
    assert out["countdown"].startswith("باقي ") and out["weekday_ok"]
    assert "AH" not in out["hijri"] and out["hijri"]
    assert out["rows"] == expected_rows("ar", out["friday"])


def test_a_city_saved_under_its_old_english_name_is_shown_with_the_transliterated_one(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def check():
            w = app._window
            out["city"] = w._date_card.city_text
            d = open_preferences()
            picker = one(d, Adw.ComboRow, "Quick pick a region")
            names = model_strings(picker)
            out["selected"] = names[picker.get_selected()]
            out["has_translated_names"] = [n for n in names if n in ("New Cairo", "Shorouk City", "Nasr City")]
            out["governorates_keep_english"] = all(n in names for n in ("Cairo", "Alexandria", "Port Said", "Luxor"))
            out["article_first"] = (
                names.index("Aswan") < names.index("El Mansoura") < names.index("El Qahira El Gedida"))
            return finish()
        GLib.timeout_add(2000, check)
    """,
        settings={"city_name": "New Cairo"},
    )
    assert "Traceback" not in err
    assert out["city"] == "📍 El Qahira El Gedida" and out["selected"] == "El Qahira El Gedida"
    assert out["has_translated_names"] == [] and out["governorates_keep_english"] and out["article_first"]


def test_polar_location_shows_a_warning_instead_of_crashing(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def check():
            out["has_window"] = app._window is not None
            out["schedule_is_none"] = app._window._schedule is None
            return finish()
        GLib.timeout_add(2500, check)
    """,
        settings={"latitude": 88.0, "longitude": 0.0, "timezone_name": "UTC", "city_name": "North Pole"},
    )
    assert out["has_window"] and out["schedule_is_none"] and "Traceback" not in err


def test_stale_day_after_suspend_is_detected_by_the_tick(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        from datetime import timedelta
        def check():
            w = app._window
            today = w._schedule.today.date
            w._schedule.today.date = today - timedelta(days=1)
            w._last_day_checked = today - timedelta(days=1)
            w._tick()
            out["refreshed_to_today"] = w._schedule.today.date == today
            return finish()
        GLib.timeout_add(2000, check)
    """,
    )
    assert out["refreshed_to_today"] and "Traceback" not in err


def test_countdown_after_isha_points_to_tomorrows_fajr_and_is_cached(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        from datetime import datetime
        def check():
            w = app._window
            late = datetime.combine(w._schedule.today.date, datetime.max.time().replace(microsecond=0))
            w._update_countdown(late)
            out["name"] = w._next_card.name_text
            first = w._schedule.tomorrow()
            w._update_countdown(late)
            out["cached"] = w._schedule.tomorrow() is first and first is not None
            out["label"] = w._next_card.countdown_text
            return finish()
        GLib.timeout_add(2000, check)
    """,
    )
    assert out["name"] == "Fajr" and out["cached"] and out["label"].startswith("Time left ")
    assert "Traceback" not in err


def test_highlight_follows_the_next_prayer_while_the_window_is_open(tmp_path):
    out, _ = run_scenario(
        tmp_path,
        """
        from datetime import datetime, timedelta
        def accented():
            return [p.value for p, label in w._prayer_list.time_labels.items() if label.has_css_class("accent")]
        def check():
            global w
            w = app._window
            t = w._schedule.today
            w._update_highlights(t.dhuhr - timedelta(hours=1))
            out["before"] = accented()
            w._update_highlights(datetime.combine(t.date, t.dhuhr.time()).replace(microsecond=1))  # just after
            out["after"] = accented()
            return finish()
        GLib.timeout_add(2000, check)
    """,
    )
    assert out["before"] == ["dhuhr"] and out["after"] == ["asr"]


def test_closing_the_window_keeps_notifications_alive_when_no_service_runs(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def close_it():
            w = app._window
            w.close()
            GLib.timeout_add(3500, after)
            return False
        def after():
            w = app._window
            out["hidden"] = not w.get_visible()
            out["engine_alive"] = app._scheduler._running
            app.activate()
            GLib.timeout_add(500, reopened)
            return False
        def reopened():
            out["visible_again"] = app._window.get_visible()
            return finish()
        GLib.timeout_add(1500, close_it)
    """,
    )
    assert out == {"hidden": True, "engine_alive": True, "visible_again": True} and "Traceback" not in err


def test_prayer_icons_and_bundled_bell_icons_all_resolve(tmp_path):
    """Regression test: Maghrib used to render distorted (``emblem-default-symbolic``).

    Every icon in use must exist in the theme.
    """
    out, err = run_scenario(
        tmp_path,
        """
        from gi.repository import Gdk
        from multazem.services.notifications import PRAYER_ICONS
        def check():
            theme = Gtk.IconTheme.get_for_display(Gdk.Display.get_default())
            out["theme_present"] = theme.has_icon("weather-clear-symbolic")
            wanted = list(PRAYER_ICONS.values()) + ["multazem-bell-symbolic", "multazem-bell-off-symbolic"]
            out["missing"] = [n for n in wanted if not theme.has_icon(n)]
            out["maghrib_icon"] = PRAYER_ICONS[Prayer.MAGHRIB]
            return finish()
        GLib.timeout_add(1500, check)
    """,
    )
    if not out["theme_present"]:
        pytest.skip("the Adwaita icon theme is not installed in this test environment (adwaita-icon-theme)")
    assert out["missing"] == [] and out["maghrib_icon"] == "daytime-sunset-symbolic" and "Traceback" not in err
