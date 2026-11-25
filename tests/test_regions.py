# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Regions and the validation of user-entered ones: names, coordinate parsing and limits."""

import pytest

from multazem.core.egypt_cities import FORMER_ENGLISH_NAMES, GOVERNORATE_CITIES
from multazem.core.regions import (
    MAX_REGION_NAME_LENGTH,
    Region,
    RegionValidationError,
    build_region,
    build_region_from_text,
    builtin_regions,
    normalize_name,
    parse_coordinate,
    sort_key,
)
from multazem.i18n import LocalizedError


def lat(text):
    """Parses a latitude the way the form does."""
    return parse_coordinate(text, field="latitude", limit=90)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("24.71", 24.71),
        ("  24.71  ", 24.71),
        ("-33.9", -33.9),
        ("+10", 10.0),
        ("5", 5.0),
        (".5", 0.5),
        ("5.", 5.0),
        ("0", 0.0),
        ("-0", 0.0),
        ("90", 90.0),
        ("-90", -90.0),
        ("24,71", 24.71),
        ("24.71°", 24.71),
        ("−33.9", -33.9),
        ("٢٤٫٧١", 24.71),
        ("۲۴.۷۱", 24.71),
    ],
)
def test_valid_coordinates_are_parsed(text, expected):
    assert lat(text) == pytest.approx(expected)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "abc",
        "nan",
        "NaN",
        "inf",
        "-inf",
        "Infinity",
        "1e1",
        "1E1",
        "0x10",
        "1,000.5",
        "--5",
        "5-",
        "5 5",
        "24.71.3",
        "٢٤ ٧١",
        ".",
        "+",
        "-",
        "٫",
        "24°N",
    ],
)
def test_non_numeric_text_is_rejected_as_invalid(text):
    with pytest.raises(RegionValidationError) as raised:
        lat(text)
    assert raised.value.field == "latitude" and raised.value.key == "region.error.latitude_invalid"


@pytest.mark.parametrize("text", ["90.01", "-90.01", "91", "1000", "99999999999999999999"])
def test_out_of_range_coordinates_are_rejected(text):
    with pytest.raises(RegionValidationError) as raised:
        lat(text)
    assert raised.value.key == "region.error.latitude_range"
    assert "90" in str(raised.value)


def test_the_limit_and_field_are_parameters():
    assert parse_coordinate("180", field="longitude", limit=180) == 180
    with pytest.raises(RegionValidationError) as raised:
        parse_coordinate("181", field="longitude", limit=180)
    assert raised.value.field == "longitude" and "180" in str(raised.value)


def test_a_valid_region_is_built_and_normalised():
    region = build_region("  Riyadh   North ", 24.71, 46.67, " Asia/Riyadh ")
    assert region.is_custom and region.timezone == "Asia/Riyadh"
    assert (region.latitude, region.longitude) == (24.71, 46.67)
    assert region.name("en") == region.name("ar") == "Riyadh North"


def test_integers_are_accepted_and_stored_as_floats():
    region = build_region("Origin", 0, 0, "UTC")
    assert isinstance(region.latitude, float) and isinstance(region.longitude, float)


def test_arabic_names_are_accepted():
    assert build_region("حي النزهة", 30.1, 31.3, "Africa/Cairo").name("en") == "حي النزهة"


@pytest.mark.parametrize("name", ["", "   ", "\n\t "])
def test_empty_names_are_rejected(name):
    with pytest.raises(RegionValidationError) as raised:
        build_region(name, 1, 1, "UTC")
    assert (raised.value.field, raised.value.key) == ("name", "region.error.name_required")


def test_name_length_limit():
    assert build_region("x" * MAX_REGION_NAME_LENGTH, 1, 1, "UTC")
    with pytest.raises(RegionValidationError) as raised:
        build_region("x" * (MAX_REGION_NAME_LENGTH + 1), 1, 1, "UTC")
    assert raised.value.key == "region.error.name_too_long" and str(MAX_REGION_NAME_LENGTH) in str(raised.value)


@pytest.mark.parametrize(
    "taken,typed",
    [
        (["Cairo"], "cairo"),
        (["Cairo"], "  CAIRO "),
        (["New Cairo"], "new   cairo"),
        (["القاهرة"], "القاهرة"),
    ],
)
def test_duplicate_names_are_rejected_ignoring_case_and_spacing(taken, typed):
    with pytest.raises(RegionValidationError) as raised:
        build_region(typed, 1, 1, "UTC", taken_names=taken)
    assert raised.value.key == "region.error.name_exists"


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (float("nan"), 0),
        (0, float("inf")),
        (-float("inf"), 0),
        (True, 0),
        ("30", 0),
        (None, 0),
        (0, "31"),
    ],
)
def test_non_numeric_coordinates_are_rejected(latitude, longitude):
    with pytest.raises(RegionValidationError) as raised:
        build_region("X", latitude, longitude, "UTC")
    assert raised.value.field in {"latitude", "longitude"} and raised.value.key.endswith("_invalid")


@pytest.mark.parametrize(
    "latitude,longitude,field",
    [(90.5, 0, "latitude"), (-91, 0, "latitude"), (0, 180.5, "longitude"), (0, -181, "longitude")],
)
def test_out_of_range_numbers_are_rejected(latitude, longitude, field):
    with pytest.raises(RegionValidationError) as raised:
        build_region("X", latitude, longitude, "UTC")
    assert raised.value.field == field and raised.value.key.endswith("_range")


@pytest.mark.parametrize("timezone", ["", "  ", "Foo/Bar", "../../etc/passwd", "/etc/passwd", "Africa"])
def test_unknown_time_zones_are_rejected(timezone):
    with pytest.raises(RegionValidationError) as raised:
        build_region("X", 1, 1, timezone)
    assert (raised.value.field, raised.value.key) == ("timezone", "region.error.timezone_invalid")


def test_boundary_coordinates_are_accepted():
    assert build_region("Pole", 90, 180, "UTC") and build_region("Pole 2", -90, -180, "UTC")


def test_text_form_parses_numbers_then_validates():
    region = build_region_from_text("Jeddah", "21.54", "39.17", "Asia/Riyadh")
    assert (region.latitude, region.longitude) == (21.54, 39.17)


def test_text_form_accepts_arabic_digits():
    region = build_region_from_text("جدة", "٢١٫٥٤", "٣٩٫١٧", "Asia/Riyadh")
    assert (region.latitude, region.longitude) == (21.54, 39.17)


@pytest.mark.parametrize(
    "args,field",
    [
        (("", "x", "y", "bad/zone"), "name"),
        (("A", "x", "y", "bad/zone"), "latitude"),
        (("A", "10", "y", "bad/zone"), "longitude"),
        (("A", "10", "20", "bad/zone"), "timezone"),
        (("A", "100", "20", "UTC"), "latitude"),
        (("A", "10", "200", "UTC"), "longitude"),
    ],
)
def test_text_form_reports_the_first_invalid_field_in_form_order(args, field):
    with pytest.raises(RegionValidationError) as raised:
        build_region_from_text(*args)
    assert raised.value.field == field


def test_validation_errors_are_localized_errors():
    with pytest.raises(LocalizedError) as raised:
        build_region_from_text("A", "ninety", "1", "UTC")
    error = raised.value
    assert isinstance(error, ValueError)
    assert "Latitude must be a number" in str(error)
    assert "خط العرض" in error.localized("ar")


def test_name_lookup_falls_back_to_english_then_to_any_name():
    region = Region(names={"en": "Home", "ar": "البيت"}, latitude=1, longitude=2, timezone="UTC")
    assert region.name("ar") == "البيت" and region.name("en") == "Home" and region.name("fr") == "Home"
    only_arabic = Region(names={"ar": "البيت"}, latitude=1, longitude=2, timezone="UTC")
    assert only_arabic.name("en") == "البيت"
    assert set(region.all_names()) == {"Home", "البيت"}


def test_builtin_regions_are_bilingual_and_not_custom():
    regions = builtin_regions()
    assert len(regions) == 245
    cairo = next(r for r in regions if r.name("en") == "Cairo")
    assert cairo.name("ar") == "القاهرة" and not cairo.is_custom and cairo.timezone == "Africa/Cairo"


@pytest.mark.parametrize(
    "arabic,english",
    [
        ("القاهرة الجديدة", "El Qahira El Gedida"),
        ("العاشر من رمضان", "El Ashir Min Ramadan"),
        ("السادس من أكتوبر", "El Sadis Min Oktobar"),
        ("رشيد", "Rashid"),
        ("سانت كاترين", "Sant Katrin"),
        ("مدينة نصر", "Madinat Nasr"),
        ("العاصمة الإدارية الجديدة", "El Asima El Idariya El Gedida"),
        ("الغردقة", "El Ghardaqa"),
        ("المنصورة", "El Mansoura"),
        ("الزقازيق", "El Zagazig"),
        ("الشروق", "El Shorouk"),
        ("الشيخ زايد", "El Sheikh Zayed"),
    ],
)
def test_english_names_are_transliterations_not_translations(arabic, english):
    by_arabic = {r.name("ar"): r for r in builtin_regions()}
    assert by_arabic[arabic].name("en") == english


@pytest.mark.parametrize(
    "arabic,english",
    [
        ("القاهرة", "Cairo"),
        ("الإسكندرية", "Alexandria"),
        ("الجيزة", "Giza"),
        ("بور سعيد", "Port Said"),
        ("السويس", "Suez"),
        ("دمياط", "Damietta"),
        ("الإسماعيلية", "Ismailia"),
        ("الأقصر", "Luxor"),
        ("أسوان", "Aswan"),
        ("الفيوم", "Fayoum"),
        ("المنيا", "Minya"),
        ("أسيوط", "Asyut"),
        ("سوهاج", "Sohag"),
        ("قنا", "Qena"),
        ("بني سويف", "Beni Suef"),
        ("كفر الشيخ", "Kafr El Sheikh"),
    ],
)
def test_governorates_keep_their_established_english_names(arabic, english):
    by_arabic = {r.name("ar"): r for r in builtin_regions()}
    assert arabic in GOVERNORATE_CITIES and by_arabic[arabic].name("en") == english


def test_the_governorate_exception_is_exactly_the_listed_cities():
    arabic_names = {r.name("ar") for r in builtin_regions()}
    assert GOVERNORATE_CITIES.issubset(arabic_names) and len(GOVERNORATE_CITIES) == 16


def test_no_other_english_name_is_a_translation_or_uses_a_foreign_article():
    translated_words = {"city", "new", "formerly", "capital", "saint", "of", "red", "sea"}
    for region in builtin_regions():
        english = region.name("en")
        assert english.isascii() and english == " ".join(english.split()), english
        if region.name("ar") in GOVERNORATE_CITIES:
            continue
        words = {word.strip("()").casefold() for word in english.split()}
        assert not words & translated_words, english
        assert not english.startswith(("Al ", "Ash ", "Al-")) and " al-" not in english, english


def test_every_arabic_name_with_the_article_starts_with_el_in_english_except_governorates():
    wrong = [
        (r.name("ar"), r.name("en"))
        for r in builtin_regions()
        if r.name("ar").startswith("ال")
        and r.name("ar") not in GOVERNORATE_CITIES
        and not r.name("en").startswith("El ")
    ]
    assert wrong == []


def test_english_names_are_unique():
    names = [normalize_name(r.name("en")) for r in builtin_regions()]
    assert len(names) == len(set(names)) == 245


def test_earlier_english_names_are_remembered_as_aliases_only():
    by_arabic = {r.name("ar"): r for r in builtin_regions()}
    new_cairo = by_arabic["القاهرة الجديدة"]
    assert new_cairo.aliases == ("New Cairo",) and "New Cairo" not in new_cairo.all_names()
    assert "New Cairo" in new_cairo.lookup_names() and "El Qahira El Gedida" in new_cairo.lookup_names()
    assert by_arabic["القاهرة"].aliases == ()
    assert FORMER_ENGLISH_NAMES["رشيد"] == "Rosetta (Rashid)"
    assert not set(FORMER_ENGLISH_NAMES) & GOVERNORATE_CITIES
    current_names = {r.name("en") for r in by_arabic.values()}
    for arabic, former in FORMER_ENGLISH_NAMES.items():
        assert former != by_arabic[arabic].name("en")
        assert former not in current_names, former


@pytest.mark.parametrize(
    "language,names,expected",
    [
        ("en", ["El Mansoura", "Aswan", "Cairo", "El Zagazig"], ["Aswan", "Cairo", "El Mansoura", "El Zagazig"]),
        ("ar", ["المنصورة", "أسوان", "القاهرة", "طنطا"], ["أسوان", "طنطا", "القاهرة", "المنصورة"]),
    ],
)
def test_sorting_ignores_the_leading_article(language, names, expected):
    assert sorted(names, key=lambda n: sort_key(n, language)) == expected


def test_normalize_name_collapses_whitespace_and_case():
    assert normalize_name("  New   CAIRO ") == "new cairo"
