# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


import io
from datetime import date, timedelta

import pytest

from multazem.core.hijri import (
    HijriDate,
    _gregorian_to_julian_day,
    _julian_day_to_hijri,
    parse_official_hijri,
    to_hijri,
)
from multazem.services import hijri_sync
from multazem.services.hijri_sync import HijriSync, fetch_official_hijri


def test_matches_independent_implementation_for_two_centuries():
    convertdate = pytest.importorskip(
        "convertdate.islamic", reason="convertdate is not installed (reference comparison only)"
    )
    day, mismatches = date(1900, 1, 1), []
    while day < date(2100, 1, 1):
        got = _julian_day_to_hijri(_gregorian_to_julian_day(day.year, day.month, day.day))
        if got != tuple(convertdate.from_gregorian(day.year, day.month, day.day)):
            mismatches.append(day)
        day += timedelta(days=1)
    assert mismatches == []


def test_always_valid_month_and_day_ranges_and_strictly_increasing():
    day, previous = date(1990, 1, 1), None
    while day < date(2060, 1, 1):
        year, month, hijri_day = _julian_day_to_hijri(_gregorian_to_julian_day(day.year, day.month, day.day))
        assert 1 <= month <= 12 and 1 <= hijri_day <= 30
        if previous:
            assert (year, month, hijri_day) > previous
        previous, day = (year, month, hijri_day), day + timedelta(days=1)


@pytest.mark.parametrize(
    "day,english,arabic",
    [
        (date(2026, 2, 18), "1 Ramadan 1447 AH", "1 رمضان 1447"),
        (date(2025, 3, 1), "1 Ramadan 1446 AH", "1 رمضان 1446"),
        (date(2026, 10, 9), "26 Rabi' al-Thani 1448 AH", "26 ربيع الآخر 1448"),
    ],
)
def test_known_anchors_in_both_languages(day, english, arabic):
    hijri = to_hijri(day)
    assert hijri.format("en") == english
    assert hijri.format("ar") == arabic


def test_format_follows_the_active_language_by_default():
    from multazem.i18n import set_language

    hijri = HijriDate(1448, 4, 26)
    assert hijri.format() == "26 Rabi' al-Thani 1448 AH"
    set_language("ar")
    assert hijri.format() == "26 ربيع الآخر 1448"


def test_hijri_dates_order_chronologically():
    assert HijriDate(1447, 12, 29) < HijriDate(1448, 1, 1) < HijriDate(1448, 1, 2)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("<div>26 ربيع الآخر 1448 هـ</div>", HijriDate(1448, 4, 26)),
        ("اليوم ٢٦ ربيع الآخر ١٤٤٨ هـ", HijriDate(1448, 4, 26)),
        ("1 رمضان 1447 هجري", HijriDate(1447, 9, 1)),
        ("26 شهر غلط 1448 هـ", None),
        ("", None),
    ],
)
def test_parse_official_hijri(text, expected):
    assert parse_official_hijri(text) == expected


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def fetch(monkeypatch, body=None, exc=None):
    def urlopen(*_args, **_kwargs):
        if exc:
            raise exc
        return Response(body.encode("utf-8"))

    monkeypatch.setattr(hijri_sync.urllib.request, "urlopen", urlopen)
    return fetch_official_hijri()


@pytest.mark.parametrize("body", ["", "<html>no date here</html>", "26 شهر غلط 1448 هـ", "x" * 10000])
def test_unparseable_pages_return_none(monkeypatch, body):
    assert fetch(monkeypatch, body) is None


@pytest.mark.parametrize("exc", [OSError("net"), TimeoutError(), ValueError("bad"), RuntimeError("x")])
def test_network_errors_return_none(monkeypatch, exc):
    assert fetch(monkeypatch, exc=exc) is None


def test_official_date_page_is_parsed(monkeypatch):
    assert fetch(monkeypatch, "<div>اليوم ٢٦ ربيع الآخر ١٤٤٨ هـ</div>") == HijriDate(1448, 4, 26)


class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self._target, self._args = target, args

    def start(self):
        self._target(*self._args)


def test_sync_fetches_once_per_day_and_reports_back(monkeypatch):
    from gi.repository import GLib

    calls, delivered = [], []
    monkeypatch.setattr(hijri_sync, "fetch_official_hijri", lambda: calls.append(1) or HijriDate(1448, 4, 26))
    monkeypatch.setattr(hijri_sync.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(GLib, "idle_add", lambda fn, *args: fn(*args))

    sync, today = HijriSync(), date(2026, 10, 9)
    assert sync.cached(today) is None
    sync.request(today, lambda day, result: delivered.append((day, result)))
    sync.request(today, lambda day, result: delivered.append((day, result)))
    assert calls == [1] and delivered == [(today, HijriDate(1448, 4, 26))]
    assert sync.cached(today) == HijriDate(1448, 4, 26)


def test_failed_sync_reports_none_and_is_retried_later(monkeypatch):
    from gi.repository import GLib

    delivered = []
    monkeypatch.setattr(hijri_sync, "fetch_official_hijri", lambda: None)
    monkeypatch.setattr(hijri_sync.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(GLib, "idle_add", lambda fn, *args: fn(*args))

    sync, today = HijriSync(), date(2026, 10, 9)
    sync.request(today, lambda day, result: delivered.append(result))
    sync.request(today, lambda day, result: delivered.append(result))
    assert delivered == [None, None] and sync.cached(today) is None
