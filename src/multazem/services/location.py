# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Automatic location detection through the user's IP address (optional, needs internet).

This is an *optional* alternative to the built-in region list, which works completely
offline. :class:`LocationManager` is used only when the user presses the "detect my
location" button.

Provider: geojs.io (``get.geojs.io``), an open-source project (Apache 2.0,
github.com/jloh/geojs) whose service is "unlimited" with no paid tier, funded by
sponsorship and donations. It was chosen on purpose over commercial services with a
"free plan + paid plan" model (such as ipapi.co or ip-api.com), in line with this project
being free and fully open source: no dependency has a commercial interest in closing or
tightening free access.

There is deliberately no fallback provider (a conscious decision, not an oversight). When
the service is down or the network is unreachable the user is told to set the location
manually from the built-in list, so the application never breaks.

History (2026-08): the code used to call ``http://ip-api.com``, which is plain HTTP even
on its free plan (HTTPS is paid). Many wireless networks and routers are stricter with
port 80 than with port 443, so detection failed frequently there.
"""

from __future__ import annotations

import http.client
import json
import math
import threading
import urllib.request
from collections.abc import Callable

from gi.repository import GLib

from ..core.coordinates import MAX_LATITUDE, MAX_LONGITUDE
from ..core.timeutil import is_valid_timezone
from ..i18n import LocalizedError, describe_error, tr

LocationCallback = Callable[[float, float, str, str], None]
ErrorCallback = Callable[[str], None]

_API_URL = "https://get.geojs.io/v1/ip/geo.json"
_REQUEST_TIMEOUT_SECONDS = 10
_MAX_RESPONSE_BYTES = 65536
_MAX_CITY_LENGTH = 60


class LocationManager:
    """Fetches the approximate location on a worker thread and reports on the GLib loop.

    Args:
        on_location: Called as ``on_location(latitude, longitude, timezone_name, city)`` on success.
        on_error: Called with a localized message when detection fails.

    Both callbacks run on the GLib main loop, exactly once per request.
    """

    def __init__(self, on_location: LocationCallback, on_error: ErrorCallback) -> None:
        self._on_location = on_location
        self._on_error = on_error

    def request(self) -> None:
        """Starts a detection on a worker thread and returns immediately."""
        threading.Thread(target=self._fetch, daemon=True).start()

    @staticmethod
    def _download() -> object:
        """Downloads and decodes the service's JSON answer (bounded in size and time).

        Raises:
            OSError: when the network or the server cannot be reached.
            ValueError: when the body is not valid JSON.
        """
        request = urllib.request.Request(_API_URL, headers={"User-Agent": "multazem/1.0"})
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(_MAX_RESPONSE_BYTES).decode("utf-8", errors="replace")
        return json.loads(body)

    def _fetch(self) -> None:
        """Worker-thread body of :meth:`request`: downloads, validates and reports the result or the error."""
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
        """Validates the service response before it can reach the settings.

        Any value used to be accepted: ``"nan"`` became ``float("nan")`` and was saved,
        a missing time zone silently turned into Africa/Cairo (wrong prayer times for
        anyone outside Egypt) and an unknown zone was stored and broke the calculation on
        every later start.

        Args:
            data: The decoded JSON document.

        Returns:
            ``(latitude, longitude, timezone_name, city)``. The city is shortened and cleaned, and replaced
            by a generic name when the service did not send one.

        Raises:
            LocalizedError: (a ``ValueError``) describing what is wrong with the response.
        """
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
        """Returns the response's latitude and longitude, requiring finite numbers within range."""
        try:
            latitude = float(data["latitude"])
            longitude = float(data["longitude"])
        except (KeyError, TypeError, ValueError):
            raise LocalizedError("location.error.invalid_coordinates") from None
        if not (math.isfinite(latitude) and math.isfinite(longitude)):
            raise LocalizedError("location.error.invalid_coordinates")
        if not (abs(latitude) <= MAX_LATITUDE and abs(longitude) <= MAX_LONGITUDE):
            raise LocalizedError("location.error.coordinates_out_of_range")
        return latitude, longitude

    def _fire_location(self, latitude: float, longitude: float, tz_name: str, city: str) -> None:
        """Delivers a successful result to ``on_location`` on the main loop."""
        GLib.idle_add(lambda: self._call_once(self._on_location, latitude, longitude, tz_name, city))

    def _fire_error(self, message: str) -> None:
        """Delivers an error message to ``on_error`` on the main loop."""
        GLib.idle_add(lambda: self._call_once(self._on_error, message))

    @staticmethod
    def _call_once(callback: Callable[..., None], *args: object) -> bool:
        """Calls ``callback(*args)`` and returns ``False``.

        ``GLib.idle_add`` repeats a callback for as long as it returns a truthy value;
        this wrapper guarantees the callback runs exactly once whatever it returns.
        """
        callback(*args)
        return False
