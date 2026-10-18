# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from multazem.core.egypt_cities import EGYPT_CITIES


def test_table_is_clean():
    assert len(EGYPT_CITIES) == 245
    for column, label in ((0, "Arabic"), (1, "English")):
        names = [city[column] for city in EGYPT_CITIES]
        assert len(set(names)) == len(names), (
            f"duplicate {label} names: the picker looks regions up by name, so a duplicate would select the wrong city"
        )
        assert all(name and name == name.strip() for name in names)


def test_names_are_in_the_expected_script():
    for arabic_name, english_name, _lat, _lon in EGYPT_CITIES:
        assert any("؀" <= char <= "ۿ" for char in arabic_name), arabic_name
        assert english_name.isascii(), english_name


def test_all_inside_egypt():
    for _ar, name, lat, lon in EGYPT_CITIES:
        assert 21.9 <= lat <= 31.7 and 24.6 <= lon <= 37.0, name


def test_no_two_cities_share_coordinates():
    coords = [(round(lat, 3), round(lon, 3)) for _ar, _en, lat, lon in EGYPT_CITIES]
    assert len(set(coords)) == len(coords)
