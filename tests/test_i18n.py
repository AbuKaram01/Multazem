# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The message catalogs: identical keys and placeholders in both languages, fallbacks and localized errors."""

import ast
import re
import string
from datetime import date, timedelta
from pathlib import Path

import pytest

from multazem import i18n
from multazem.core.calculation import CalculationMethod
from multazem.core.prayers import Prayer
from multazem.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_NAMES,
    SUPPORTED_LANGUAGES,
    LocalizedError,
    ar,
    current_language,
    describe_error,
    en,
    is_rtl,
    normalize_language,
    set_language,
    tr,
)
from multazem.services.scheduler import MESSAGE_KEYS

SOURCE_ROOT = Path(__file__).resolve().parent.parent / "src" / "multazem"
ARABIC_LETTERS = re.compile(r"[؀-ۿ]")
BRAND_NAME = "Multazem"
WEEK = [date(2026, 10, 5) + timedelta(days=i) for i in range(7)]


def placeholders(template: str) -> set[str]:
    """Returns the names of the ``{placeholders}`` of a message template."""
    return {name for _, name, _, _ in string.Formatter().parse(template) if name is not None}


def test_both_catalogs_define_exactly_the_same_keys():
    assert set(en.MESSAGES) == set(ar.MESSAGES)


def test_placeholders_match_between_languages():
    mismatched = {
        key: (placeholders(en.MESSAGES[key]), placeholders(ar.MESSAGES[key]))
        for key in en.MESSAGES
        if placeholders(en.MESSAGES[key]) != placeholders(ar.MESSAGES[key])
    }
    assert mismatched == {}


def test_every_message_is_a_valid_template():
    for catalog in (en.MESSAGES, ar.MESSAGES):
        for key, template in catalog.items():
            assert template.strip(), key
            list(string.Formatter().parse(template))


def test_english_messages_contain_no_arabic_and_arabic_ones_do():
    assert [k for k, v in en.MESSAGES.items() if ARABIC_LETTERS.search(v)] == []
    prose_without_arabic = [
        k for k, v in ar.MESSAGES.items() if not ARABIC_LETTERS.search(v) and "{" not in v and v != BRAND_NAME
    ]
    assert prose_without_arabic == []


def _literal_translation_keys() -> dict[str, str]:
    """Returns every message key the source code uses literally, mapped to the file that uses it."""
    found: dict[str, str] = {}
    for path in SOURCE_ROOT.rglob("*.py"):
        if "i18n" in path.relative_to(SOURCE_ROOT).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            function = node.func
            name = function.id if isinstance(function, ast.Name) else getattr(function, "attr", None)
            first = node.args[0]
            if name in {"tr", "LocalizedError"} and isinstance(first, ast.Constant) and isinstance(first.value, str):
                found[first.value] = str(path.relative_to(SOURCE_ROOT))
    return found


def test_every_key_used_in_the_code_exists_in_the_catalogs():
    missing = {key: where for key, where in _literal_translation_keys().items() if key not in en.MESSAGES}
    assert missing == {}


def test_dynamic_key_families_are_complete():
    expected = {prayer.label_key for prayer in Prayer}
    expected |= {prayer.label_key_on(day) for prayer in Prayer for day in WEEK}
    expected |= {method.label_key for method in CalculationMethod}
    expected |= {f"weekday.{index}" for index in range(7)}
    expected |= {f"hijri.month.{month}" for month in range(1, 13)}
    expected |= {f"window.hijri.tooltip.{kind}" for kind in ("estimated", "official")}
    expected |= {f"{key}.{part}" for key in MESSAGE_KEYS.values() for part in ("title", "body")}
    expected |= {
        "region.error.name_required",
        "region.error.name_too_long",
        "region.error.name_exists",
        "region.error.latitude_invalid",
        "region.error.latitude_range",
        "region.error.longitude_invalid",
        "region.error.longitude_range",
        "region.error.timezone_invalid",
    }
    assert expected <= set(en.MESSAGES)


def test_no_unused_messages_remain():
    used = set(_literal_translation_keys())
    dynamic_prefixes = (
        "prayer.",
        "method.",
        "weekday.",
        "hijri.month.",
        "notification.",
        "window.hijri.tooltip.",
        "region.error.",
        "prefs.latitude",
        "prefs.longitude",
        "window.toast.bell_",
    )
    unused = [k for k in en.MESSAGES if k not in used and not k.startswith(dynamic_prefixes)]
    assert unused == []


def test_english_is_the_default_language():
    assert DEFAULT_LANGUAGE == "en" == current_language()
    assert tr("window.next_prayer") == "Next prayer"


def test_switching_language_changes_the_text_and_the_direction():
    assert not is_rtl()
    assert set_language("ar") == "ar" and current_language() == "ar" and is_rtl()
    assert tr("window.next_prayer") == "الصلاة القادمة"
    set_language("en")
    assert tr("window.next_prayer") == "Next prayer" and not is_rtl()


def test_explicit_language_does_not_touch_the_global_one():
    assert tr("prayer.fajr", language="ar") == "الفجر"
    assert current_language() == "en"
    assert tr("prayer.fajr") == "Fajr"


@pytest.mark.parametrize("bad", ["fr", "", None, 5, "EN", ["ar"]])
def test_unknown_languages_fall_back_to_english(bad):
    assert normalize_language(bad) == "en"
    assert set_language(bad) == "en"
    assert tr("prayer.fajr", language=bad) == "Fajr"


def test_unknown_key_falls_back_to_the_key_itself():
    assert tr("no.such.key") == "no.such.key"
    assert tr("no.such.key", language="ar", x=1) == "no.such.key"


def test_missing_arabic_key_falls_back_to_english(monkeypatch):
    patched = dict(ar.MESSAGES)
    del patched["prayer.fajr"]
    monkeypatch.setitem(i18n._CATALOGS, "ar", patched)
    assert tr("prayer.fajr", language="ar") == "Fajr"


def test_placeholder_mismatch_never_raises():
    assert tr("window.bell.on", prayer="Fajr") == "Fajr notifications: on (click to turn off)"
    assert tr("window.bell.on") == "{prayer} notifications: on (click to turn off)"


def test_jumuah_and_sunrise_texts_exist_in_both_languages():
    assert tr("prayer.jumuah", language="en") == "Jumu'ah" and tr("prayer.jumuah", language="ar") == "الجمعة"
    assert tr("notification.sunrise.title", language="en") == "Sunrise"
    assert tr("notification.sunrise.title", language="ar") == "الشروق"
    for language in ("en", "ar"):
        body = tr("notification.sunrise.body", language=language, time="06:54")
        assert "06:54" in body and "{" not in body
        reminder = tr("notification.sunrise_reminder.body", language=language, minutes=7)
        assert "7" in reminder and "{" not in reminder


def test_sunrise_is_never_called_a_prayer_in_its_notifications():
    for key in ("notification.sunrise.title", "notification.sunrise.body", "notification.sunrise_reminder.title"):
        assert "prayer" not in en.MESSAGES[key].lower()
        assert "صلاة" not in ar.MESSAGES[key]


def test_bell_texts_read_naturally_for_sunrise_and_jumuah_in_arabic():
    assert tr("window.bell.on", language="ar", prayer="الشروق") == "إشعارات الشروق: مفعّلة (اضغط للإيقاف)"
    assert tr("window.toast.bell_off", language="ar", prayer="الجمعة") == "إشعارات الجمعة: متوقفة"
    assert tr("window.toast.bell_on", language="en", prayer="Sunrise") == "Sunrise notifications: on"


def test_language_names_are_written_in_their_own_language():
    assert LANGUAGE_NAMES == {"en": "English", "ar": "العربية"}
    assert SUPPORTED_LANGUAGES == ("en", "ar")


def test_countdown_and_date_formats_in_both_languages():
    assert tr("window.countdown", hours=1, minutes=2, seconds=3) == "Time left 01:02:03"
    assert tr("window.countdown", language="ar", hours=1, minutes=2, seconds=3) == "باقي 01:02:03"


def test_weekday_names_cover_the_whole_week_in_both_languages():
    english = [tr(f"weekday.{i}", language="en") for i in range(7)]
    arabic = [tr(f"weekday.{i}", language="ar") for i in range(7)]
    assert english[date(2026, 10, 15).weekday()] == "Thursday"
    assert arabic[date(2026, 10, 15).weekday()] == "الخميس"
    assert len(set(english)) == len(set(arabic)) == 7


def test_localized_error_is_english_in_str_and_translated_on_demand():
    error = LocalizedError("error.latitude_out_of_range", latitude=95)
    assert isinstance(error, ValueError)
    assert "95" in str(error) and "outside the valid range" in str(error)
    assert "خارج النطاق" in error.localized("ar") and "95" in error.localized("ar")
    set_language("ar")
    assert str(error).startswith("Latitude")
    assert "خارج النطاق" in error.localized()


def test_describe_error_handles_plain_exceptions():
    assert describe_error(RuntimeError("boom")) == "boom"
    assert describe_error(LocalizedError("service.installed"), "ar").endswith("تم تثبيت الخدمة وتشغيلها")
