# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Adding custom regions from the preferences dialog (real GTK app under Xvfb)."""

import json

import pytest

from gui_support import run_scenario

pytestmark = pytest.mark.gui


_ADD_REGION_SCRIPT = """
def add_button(d):
    return [b for b in walk(d, []) if isinstance(b, Gtk.Button) and b.get_label() == "Add"][0]
def step1():
    d = open_preferences()
    row = one(d, AddRegionRow)
    out["tz_prefilled"] = row._timezone_row.get_text()
    out["picker_count_before"] = len(model_strings(one(d, Adw.ComboRow, "Quick pick a region")))
    # 1) an invalid latitude is flagged and nothing changes
    row._name_row.set_text("Riyadh North")
    row._latitude_row.set_text("abc")
    row._longitude_row.set_text("46.67")
    add_button(d).emit("clicked")
    out["lat_flagged"] = row._latitude_row.has_css_class("error")
    out["name_not_flagged"] = not row._name_row.has_css_class("error")
    out["nothing_added_on_error"] = app._catalog.custom_regions == ()
    out["city_unchanged"] = app._settings.city_name == "Cairo"
    # 2) a duplicate of a built-in name is flagged on the name field
    row._name_row.set_text("cairo")
    row._latitude_row.set_text("24.71")
    add_button(d).emit("clicked")
    out["duplicate_flagged"] = row._name_row.has_css_class("error")
    # 3) a valid region
    row._name_row.set_text("  Riyadh   North ")
    row._timezone_row.set_text("Asia/Riyadh")
    add_button(d).emit("clicked")
    st = app._settings
    picker = one(d, Adw.ComboRow, "Quick pick a region")
    out["catalog_names"] = [r.name("en") for r in app._catalog.custom_regions]
    out["settings"] = [st.city_name, st.latitude, st.longitude, st.timezone_name]
    out["picker_first"] = model_strings(picker)[0]
    out["picker_selected"] = picker.get_selected()
    out["picker_count_after"] = len(model_strings(picker))
    out["form_cleared"] = [
        row._name_row.get_text(), row._latitude_row.get_text(), row._longitude_row.get_text()]
    out["form_collapsed"] = not row.get_expanded()
    out["location_rows"] = [
        one(d, Adw.EntryRow, "City name").get_text(), one(d, Adw.SpinRow, "Latitude").get_value()]
    d.close()
    GLib.timeout_add(700, step2); return False
def step2():
    out["main_city"] = app._window._date_card.city_text
    out["main_tz"] = app._window._schedule.tz_name
    return finish()
GLib.timeout_add(1500, step1)
"""


_ADD_REGION_RESTART_SCRIPT = """
def check():
    d = open_preferences()
    picker = one(d, Adw.ComboRow, "Quick pick a region")
    out["picker_first"] = model_strings(picker)[0]
    out["picker_selected"] = picker.get_selected()
    out["picker_subtitle"] = picker.get_subtitle()
    return finish()
GLib.timeout_add(2000, check)
"""


def test_adding_a_region_from_the_preferences_makes_it_current_and_persists_it(tmp_path):
    first, err1 = run_scenario(tmp_path, _ADD_REGION_SCRIPT)
    assert "Traceback" not in err1
    assert first["tz_prefilled"] == "Africa/Cairo"
    assert (
        first["lat_flagged"]
        and first["name_not_flagged"]
        and first["nothing_added_on_error"]
        and first["city_unchanged"]
    )
    assert first["duplicate_flagged"]
    assert first["catalog_names"] == ["Riyadh North"]
    assert first["settings"] == ["Riyadh North", 24.71, 46.67, "Asia/Riyadh"]
    assert first["picker_first"] == "Riyadh North" and first["picker_selected"] == 0
    assert first["picker_count_after"] == first["picker_count_before"] + 1
    assert first["form_cleared"] == ["", "", ""] and first["form_collapsed"]
    assert first["location_rows"] == ["Riyadh North", 24.71]
    assert first["main_city"] == "📍 Riyadh North" and first["main_tz"] == "Asia/Riyadh"

    stored = json.loads((tmp_path / "cfg" / "multazem" / "regions.json").read_text(encoding="utf-8"))
    assert stored["regions"] == [
        {"name": "Riyadh North", "latitude": 24.71, "longitude": 46.67, "timezone": "Asia/Riyadh"}
    ]

    second, err2 = run_scenario(tmp_path, _ADD_REGION_RESTART_SCRIPT)
    assert second["picker_first"] == "Riyadh North" and second["picker_selected"] == 0
    assert second["picker_subtitle"].startswith("246 regions") and "Traceback" not in err2


_ADD_REGION_ARABIC_DIGITS_SCRIPT = """
def step1():
    d = open_preferences()
    row = one(d, AddRegionRow)
    out["title"] = row.get_title()
    row._name_row.set_text("حي الواحة")
    row._latitude_row.set_text("٣٠٫٥")
    row._longitude_row.set_text("٣١٫٢")
    [b for b in walk(d, []) if isinstance(b, Gtk.Button) and b.get_label() == "إضافة"][0].emit("clicked")
    st = app._settings
    out["settings"] = [st.city_name, st.latitude, st.longitude]
    picker = one(d, Adw.ComboRow, "اختيار سريع لمنطقة")
    out["picker_first"] = model_strings(picker)[0]
    out["subtitle"] = picker.get_subtitle()
    # a bad value reports the error in Arabic and flags the field
    row._name_row.set_text("مكان آخر")
    row._latitude_row.set_text("ليس رقما")
    row._longitude_row.set_text("10")
    row._submit()
    out["lat_flagged"] = row._latitude_row.has_css_class("error")
    return finish()
GLib.timeout_add(1500, step1)
"""


def test_adding_a_region_with_arabic_digits_in_the_arabic_ui(tmp_path):
    out, err = run_scenario(
        tmp_path,
        _ADD_REGION_ARABIC_DIGITS_SCRIPT,
        settings={"language": "ar"},
    )
    assert out["title"] == "إضافة منطقة" and "Traceback" not in err
    assert out["settings"] == ["حي الواحة", 30.5, 31.2] and out["picker_first"] == "حي الواحة"
    assert out["subtitle"].startswith("246 منطقة") and out["lat_flagged"]


def test_a_custom_region_keeps_its_name_when_the_language_changes(tmp_path):
    out, err = run_scenario(
        tmp_path,
        """
        def step1():
            d = open_preferences()
            row = one(d, AddRegionRow)
            row._name_row.set_text("My Farm")
            row._latitude_row.set_text("30.1")
            row._longitude_row.set_text("31.1")
            row._submit()
            app._settings.language = "ar"
            GLib.timeout_add(900, step2); return False
        def step2():
            w = app._window
            out["city"] = w._date_card.city_text
            picker = one(w._pref_dialog, Adw.ComboRow, "اختيار سريع لمنطقة")
            out["picker_first"] = model_strings(picker)[0]
            out["picker_selected"] = picker.get_selected()
            return finish()
        GLib.timeout_add(1500, step1)
    """,
    )
    assert out == {"city": "📍 My Farm", "picker_first": "My Farm", "picker_selected": 0} and "Traceback" not in err
