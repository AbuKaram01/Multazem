# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


import json

import pytest

from multazem.core.regions import RegionValidationError, sort_key
from multazem.i18n import LocalizedError
from multazem.services import region_catalog
from multazem.services.region_catalog import RegionCatalog


def test_a_fresh_catalog_offers_only_the_builtin_regions(catalog, regions_path):
    assert catalog.custom_regions == ()
    assert len(catalog.regions("en")) == 245
    assert not regions_path.exists()


def test_adding_a_region_makes_it_available_and_persists_it(catalog, regions_path):
    region = catalog.add("Riyadh North", "24.7136", "46.6753", "Asia/Riyadh")
    assert region.is_custom and region in catalog.regions("en")
    document = json.loads(regions_path.read_text(encoding="utf-8"))
    assert document == {
        "version": 1,
        "regions": [{"name": "Riyadh North", "latitude": 24.7136, "longitude": 46.6753, "timezone": "Asia/Riyadh"}],
    }


def test_added_regions_survive_a_restart(catalog, regions_path):
    catalog.add("Home", "30.1", "31.2", "Africa/Cairo")
    catalog.add("حي الزهور", "30.2", "31.3", "Africa/Cairo")
    reopened = RegionCatalog(regions_path)
    assert [r.name("en") for r in reopened.custom_regions] == ["Home", "حي الزهور"]
    assert reopened.custom_regions[1].latitude == 30.2 and reopened.custom_regions[1].is_custom


def test_custom_regions_are_listed_first_in_both_languages(catalog):
    catalog.add("Zebra Town", "30", "31", "Africa/Cairo")
    catalog.add("Alpha Town", "31", "32", "Africa/Cairo")
    for language in ("en", "ar"):
        names = [r.name(language) for r in catalog.regions(language)]
        assert names[:2] == ["Zebra Town", "Alpha Town"]
        assert len(names) == 247


def test_builtin_regions_are_sorted_by_the_name_in_the_active_language(catalog):
    english = [sort_key(r.name("en"), "en") for r in catalog.regions("en")]
    arabic = [sort_key(r.name("ar"), "ar") for r in catalog.regions("ar")]
    assert english == sorted(english) and arabic == sorted(arabic)
    assert english != [sort_key(r.name("en"), "en") for r in catalog.regions("ar")]


def test_the_leading_article_does_not_decide_the_order(catalog):
    english = [r.name("en") for r in catalog.regions("en")]
    assert (
        english.index("Aswan")
        < english.index("El Mansoura")
        < english.index("El Qahira El Gedida")
        < english.index("El Zagazig")
    )
    arabic = [r.name("ar") for r in catalog.regions("ar")]
    assert arabic.index("أسوان") < arabic.index("طنطا") < arabic.index("القاهرة") < arabic.index("المنصورة")


def test_lookup_works_by_any_language_and_ignores_case(catalog):
    cairo = catalog.find_by_name("cairo")
    assert cairo is not None and catalog.find_by_name("القاهرة") is cairo
    assert catalog.find_by_name("  CAIRO ") is cairo
    mansoura = catalog.find_by_name("el mansoura")
    assert mansoura is not None and catalog.find_by_name("المنصورة") is mansoura
    assert catalog.find_by_name("  EL   MANSOURA ") is mansoura
    assert catalog.find_by_name("Atlantis") is None
    custom = catalog.add("Home Base", "1", "2", "UTC")
    assert catalog.find_by_name("home base") is custom


def test_names_saved_by_an_earlier_version_are_still_recognised(catalog):
    current = catalog.find_by_name("El Qahira El Gedida")
    assert catalog.find_by_name("New Cairo") is current and catalog.find_by_name("new cairo") is current
    assert catalog.display_name("New Cairo", "en") == "El Qahira El Gedida"
    assert catalog.display_name("New Cairo", "ar") == "القاهرة الجديدة"
    assert catalog.display_name("Rosetta (Rashid)", "en") == "Rashid"
    assert catalog.display_name("10th of Ramadan City", "en") == "El Ashir Min Ramadan"
    assert catalog.display_name("Alexandria", "en") == "Alexandria"


def test_display_name_follows_the_language(catalog):
    assert catalog.display_name("القاهرة", "en") == "Cairo"
    assert catalog.display_name("Cairo", "ar") == "القاهرة"
    assert catalog.display_name("المنصورة", "en") == "El Mansoura"
    assert catalog.display_name("El Mansoura", "ar") == "المنصورة"
    assert catalog.display_name("Some Unknown Place", "ar") == "Some Unknown Place"
    catalog.add("Home Base", "1", "2", "UTC")
    assert catalog.display_name("Home Base", "ar") == "Home Base"


@pytest.mark.parametrize("name", ["Cairo", "cairo", "القاهرة", "  New   Cairo "])
def test_builtin_names_cannot_be_reused(catalog, name):
    with pytest.raises(RegionValidationError) as raised:
        catalog.add(name, "30", "31", "Africa/Cairo")
    assert raised.value.field == "name" and catalog.custom_regions == ()


def test_custom_names_cannot_be_added_twice(catalog):
    catalog.add("Home", "1", "2", "UTC")
    with pytest.raises(RegionValidationError) as raised:
        catalog.add("HOME", "3", "4", "UTC")
    assert raised.value.key == "region.error.name_exists" and len(catalog.custom_regions) == 1


@pytest.mark.parametrize(
    "args,field",
    [
        (("", "1", "2", "UTC"), "name"),
        (("X", "abc", "2", "UTC"), "latitude"),
        (("X", "1", "999", "UTC"), "longitude"),
        (("X", "1", "2", "Nope/Zone"), "timezone"),
    ],
)
def test_invalid_input_adds_nothing_and_names_the_field(catalog, regions_path, args, field):
    with pytest.raises(RegionValidationError) as raised:
        catalog.add(*args)
    assert raised.value.field == field
    assert catalog.custom_regions == () and not regions_path.exists()


def test_a_failed_save_adds_nothing_and_reports_a_localized_error(catalog, monkeypatch):
    def boom(path, payload):
        raise OSError("disk full")

    monkeypatch.setattr(region_catalog, "write_json_atomic", boom)
    with pytest.raises(LocalizedError) as raised:
        catalog.add("Home", "1", "2", "UTC")
    assert "disk full" in str(raised.value) and raised.value.key == "region.error.save_failed"
    assert catalog.custom_regions == ()
    monkeypatch.undo()
    assert catalog.add("Home", "1", "2", "UTC")


def test_saving_leaves_no_temporary_files(catalog, regions_path):
    catalog.add("Home", "1", "2", "UTC")
    assert [p.name for p in regions_path.parent.iterdir()] == ["regions.json"]


def test_a_corrupt_file_is_backed_up_and_ignored(regions_path, capsys):
    regions_path.parent.mkdir(parents=True)
    regions_path.write_text("{not json", encoding="utf-8")
    catalog = RegionCatalog(regions_path)
    assert catalog.custom_regions == ()
    assert regions_path.with_name("regions.json.corrupt").read_text(encoding="utf-8") == "{not json"
    assert "corrupt" in capsys.readouterr().err
    catalog.add("Home", "1", "2", "UTC")
    assert [r.name("en") for r in RegionCatalog(regions_path).custom_regions] == ["Home"]


@pytest.mark.parametrize("content", ["[]", "null", '"text"', "42", '{"regions": 5}', '{"version": 1}'])
def test_files_of_the_wrong_shape_are_treated_as_corrupt(regions_path, content):
    regions_path.parent.mkdir(parents=True)
    regions_path.write_text(content, encoding="utf-8")
    assert RegionCatalog(regions_path).custom_regions == ()
    assert regions_path.with_name("regions.json.corrupt").exists()


def test_invalid_entries_are_skipped_but_valid_ones_are_kept(regions_path, capsys):
    regions_path.parent.mkdir(parents=True)
    good = {"name": "Good", "latitude": 10, "longitude": 20, "timezone": "UTC"}
    entries = [
        good,
        "not an object",
        {"name": "No coordinates", "timezone": "UTC"},
        {"name": "Bad latitude", "latitude": 99, "longitude": 0, "timezone": "UTC"},
        {"name": "Bad zone", "latitude": 1, "longitude": 1, "timezone": "Nope/Zone"},
        {"name": 5, "latitude": 1, "longitude": 1, "timezone": "UTC"},
        {"name": "NaN lat", "latitude": float("nan"), "longitude": 1, "timezone": "UTC"},
        {"name": "good", "latitude": 1, "longitude": 1, "timezone": "UTC"},
        {"name": "Cairo", "latitude": 1, "longitude": 1, "timezone": "UTC"},
        {"name": "Also Good", "latitude": -5.5, "longitude": 120.25, "timezone": "Asia/Makassar"},
    ]
    regions_path.write_text(json.dumps({"version": 1, "regions": entries}), encoding="utf-8")
    catalog = RegionCatalog(regions_path)
    assert [r.name("en") for r in catalog.custom_regions] == ["Good", "Also Good"]
    assert capsys.readouterr().err.count("Skipping an invalid custom region") == len(entries) - 2


def test_an_unreadable_file_is_not_overwritten(regions_path, monkeypatch, capsys):
    from pathlib import Path

    regions_path.parent.mkdir(parents=True)
    regions_path.write_text(json.dumps({"version": 1, "regions": []}), encoding="utf-8")
    before = regions_path.read_bytes()
    real = Path.read_bytes

    def deny(self):
        if self == regions_path:
            raise PermissionError(13, "denied")
        return real(self)

    monkeypatch.setattr(Path, "read_bytes", deny)
    catalog = RegionCatalog(regions_path)
    assert catalog.custom_regions == () and "Could not read" in capsys.readouterr().err
    monkeypatch.undo()
    assert regions_path.read_bytes() == before


def test_the_default_location_follows_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    RegionCatalog().add("Home", "1", "2", "UTC")
    assert (tmp_path / "xdg" / "multazem" / "regions.json").exists()
