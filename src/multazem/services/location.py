# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

import http.client
import json
import math
import threading
import urllib.request
from collections.abc import Callable

from gi.repository import GLib

from ..core.timeutil import is_valid_timezone
from ..i18n import LocalizedError, describe_error, tr

LocationCallback = Callable[[float, float, str, str], None]
ErrorCallback = Callable[[str], None]

_API_URL = "https://get.geojs.io/v1/ip/geo.json"
_REQUEST_TIMEOUT_SECONDS = 10
_MAX_RESPONSE_BYTES = 65536
_MAX_CITY_LENGTH = 60


class LocationManager:
    def __init__(self, on_location: LocationCallback, on_error: ErrorCallback) -> None:
        self._on_location = on_location
        self._on_error = on_error

    def request(self) -> None:
        threading.Thread(target=self._fetch, daemon=True).start()

    @staticmethod
    def _download() -> object:
        request = urllib.request.Request(_API_URL, headers={"User-Agent": "multazem/1.0"})
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
        return json.loads(body)

    def _fetch(self) -> None:
        try:
            data = self._download()
        except OSError:
            self._fire_error(tr("location.error.offline"))
            return
        except (ValueError, http.client.HTTPException):
            self._fire_error(tr("location.error.unreadable"))
            return

        try:
            latitude, longitude, tz_name, city = self.parse_response(data)
        except LocalizedError as error:
            self._fire_error(tr("location.error.with_hint", reason=describe_error(error)))
            return
        self._fire_location(latitude, longitude, tz_name, city)

    @staticmethod
    def parse_response(data: object) -> tuple[float, float, str, str]:
        if not isinstance(data, dict):
            raise LocalizedError("location.error.unexpected_response")
        latitude, longitude = LocationManager._parse_coordinates(data)
        tz_name = str(data.get("timezone") or "").strip()
        if not is_valid_timezone(tz_name):
            raise LocalizedError("location.error.invalid_timezone")
        city = " ".join(str(data.get("city") or "").split())[:_MAX_CITY_LENGTH]
        return latitude, longitude, tz_name, city or tr("location.default_city")

    @staticmethod
    def _parse_coordinates(data: dict) -> tuple[float, float]:
        try:
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
        except (KeyError, TypeError, ValueError):
            raise LocalizedError("location.error.invalid_coordinates") from None
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            raise LocalizedError("location.error.invalid_coordinates")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise LocalizedError("location.error.coordinates_out_of_range")
        return latitude, longitude

    def _fire_location(self, latitude: float, longitude: float, tz_name: str, city: str) -> None:
        GLib.idle_add(lambda: self._call_once(self._on_location, latitude, longitude, tz_name, city))

    def _fire_error(self, message: str) -> None:
        GLib.idle_add(lambda: self._call_once(self._on_error, message))

    @staticmethod
    def _call_once(callback: Callable[..., None], *args: object) -> bool:
        callback(*args)
        return False
