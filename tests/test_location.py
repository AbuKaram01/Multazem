# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


import io
import json
import urllib.error

import pytest

from multazem.i18n import set_language
from multazem.services import location as loc
from multazem.services.location import LocationManager


@pytest.mark.parametrize(
    "data",
    [
        {"latitude": "nan", "longitude": "31", "timezone": "Africa/Cairo"},
        {"latitude": "inf", "longitude": "31", "timezone": "Africa/Cairo"},
        {"latitude": "95", "longitude": "0", "timezone": "UTC"},
        {"latitude": "0", "longitude": "-181", "timezone": "UTC"},
        {"latitude": "30", "longitude": "31"},
        {"latitude": "30", "longitude": "31", "timezone": "Mars/Olympus"},
        {"latitude": None, "longitude": 1, "timezone": "UTC"},
        {"longitude": 1},
        [],
        None,
        "x",
        5,
    ],
)
def test_bad_service_responses_are_rejected(data):
    with pytest.raises(ValueError):
        LocationManager.parse_response(data)


def test_good_response_is_normalised():
    lat, lon, tz, city = LocationManager.parse_response(
        {"latitude": "51.5", "longitude": "-0.12", "timezone": "Europe/London", "city": "  Lon\ndon  " + "x" * 200}
    )
    assert (lat, lon, tz) == (51.5, -0.12, "Europe/London")
    assert city.startswith("Lon don") and len(city) <= 60


def test_unnamed_city_falls_back_to_a_localized_label():
    response = {"latitude": 1, "longitude": 2, "timezone": "UTC"}
    assert LocationManager.parse_response(response)[3] == "Your current location"
    set_language("ar")
    assert LocationManager.parse_response(response)[3] == "موقعك الحالي"


def test_rejection_reasons_are_localizable():
    with pytest.raises(ValueError) as raised:
        LocationManager.parse_response({"latitude": "30", "longitude": "31"})
    assert "time zone" in str(raised.value)
    assert "منطقة زمنية" in raised.value.localized("ar")


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def run_fetch(monkeypatch, urlopen):
    got = {}
    monkeypatch.setattr(loc.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(loc.GLib, "idle_add", lambda fn, *args: fn(*args))
    manager = LocationManager(lambda *args: got.setdefault("ok", args), lambda msg: got.setdefault("err", msg))
    manager._fetch()
    return got


def test_fetch_success(monkeypatch):
    body = json.dumps({"latitude": "30.04", "longitude": "31.23", "timezone": "Africa/Cairo", "city": "Cairo"}).encode()
    got = run_fetch(monkeypatch, lambda *a, **k: Response(body))
    assert got == {"ok": (30.04, 31.23, "Africa/Cairo", "Cairo")}


@pytest.mark.parametrize("exc", [urllib.error.URLError("dns"), TimeoutError(), ConnectionResetError()])
def test_network_failures_report_offline(monkeypatch, exc):
    def boom(*_args, **_kwargs):
        raise exc

    assert "No internet connection" in run_fetch(monkeypatch, boom)["err"]


def test_network_failure_message_follows_the_language(monkeypatch):
    set_language("ar")

    def boom(*_args, **_kwargs):
        raise TimeoutError()

    assert "الإنترنت" in run_fetch(monkeypatch, boom)["err"]


@pytest.mark.parametrize("body", [b"<html>captive portal</html>", b"", b"\xff\xfe", b'{"latitude": "x"}', b"[]"])
def test_garbage_responses_report_an_error_without_crashing(monkeypatch, body):
    got = run_fetch(monkeypatch, lambda *a, **k: Response(body))
    assert "err" in got and "ok" not in got and "manually" in got["err"]


def test_idle_callbacks_run_once_even_if_they_return_truthy():
    assert LocationManager._call_once(lambda: True) is False
