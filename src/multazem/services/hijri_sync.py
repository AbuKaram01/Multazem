# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

import threading
import urllib.request
from collections.abc import Callable
from datetime import date

from gi.repository import GLib

from ..core.hijri import HijriDate, parse_official_hijri

_DAR_ALIFTA_URL = "https://www.dar-alifta.org/ar/prayer"
_REQUEST_TIMEOUT_SECONDS = 8
_MAX_PAGE_BYTES = 2_000_000

HijriResultCallback = Callable[[date, HijriDate | None], None]


def fetch_official_hijri() -> HijriDate | None:
    try:
        request = urllib.request.Request(_DAR_ALIFTA_URL, headers={"User-Agent": "multazem/1.0"})
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            page = response.read(_MAX_PAGE_BYTES).decode("utf-8", errors="ignore")
        return parse_official_hijri(page)
    except Exception:  # noqa: BLE001 - a best-effort lookup: any failure means "use the calculated date"
        return None


class HijriSync:
    def __init__(self) -> None:
        self._cache: dict[date, HijriDate] = {}
        self._fetching: set[date] = set()

    def cached(self, day: date) -> HijriDate | None:
        return self._cache.get(day)

    def request(self, day: date, on_result: HijriResultCallback) -> None:
        if day in self._cache or day in self._fetching:
            return
        self._fetching.add(day)
        threading.Thread(target=self._fetch, args=(day, on_result), daemon=True).start()

    def _fetch(self, day: date, on_result: HijriResultCallback) -> None:
        result = fetch_official_hijri()
        if result:
            self._cache[day] = result
        GLib.idle_add(self._deliver, day, result, on_result)

    def _deliver(self, day: date, result: HijriDate | None, on_result: HijriResultCallback) -> bool:
        self._fetching.discard(day)
        on_result(day, result)
        return False
