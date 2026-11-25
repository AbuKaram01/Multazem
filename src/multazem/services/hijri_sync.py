# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Optional synchronisation of the Hijri date with Dar al-Ifta al-Misriyyah (needs internet).

Used only when the user enabled the ``sync_hijri_online`` setting; the offline estimate
in :mod:`multazem.core.hijri` stays the default and the fallback.
"""

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
    """Fetches today's officially announced Hijri date.

    Returns ``None`` when there is no internet or the page layout changed. It never
    raises, so callers can always fall back to the local calculation safely. The response size
    and the wait are bounded.
    """
    try:
        request = urllib.request.Request(_DAR_ALIFTA_URL, headers={"User-Agent": "multazem/1.0"})
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            page = response.read(_MAX_PAGE_BYTES).decode("utf-8", errors="ignore")
        return parse_official_hijri(page)
    except Exception:  # noqa: BLE001 - a best-effort lookup: any failure means "use the calculated date"
        return None


class HijriSync:
    """In-memory cache plus a background fetch, in the style of ``LocationManager``.

    Once the official date of a given day is known there is no need to ask the network
    for the same day again.
    """

    def __init__(self) -> None:
        self._cache: dict[date, HijriDate] = {}
        self._fetching: set[date] = set()

    def cached(self, day: date) -> HijriDate | None:
        """Returns the official date already fetched for ``day``, or ``None``."""
        return self._cache.get(day)

    def request(self, day: date, on_result: HijriResultCallback) -> None:
        """Fetches the official date in the background without freezing the UI.

        Does nothing when ``day`` is cached or a fetch for it is already running.
        ``on_result`` always runs on the GTK main thread (through ``GLib.idle_add``),
        also when the fetch failed (with ``None``), so the caller decides what to do.

        Args:
            day: The day the date is wanted for; the answer is cached under it.
            on_result: Called as ``on_result(day, hijri_or_none)``.
        """
        if day in self._cache or day in self._fetching:
            return
        self._fetching.add(day)
        threading.Thread(target=self._fetch, args=(day, on_result), daemon=True).start()

    def _fetch(self, day: date, on_result: HijriResultCallback) -> None:
        """Worker-thread body of :meth:`request`: fetches, caches a success and schedules the callback."""
        result = fetch_official_hijri()
        if result:
            self._cache[day] = result
        GLib.idle_add(self._deliver, day, result, on_result)

    def _deliver(self, day: date, result: HijriDate | None, on_result: HijriResultCallback) -> bool:
        """Runs on the main loop: forgets the pending fetch and calls the callback once."""
        self._fetching.discard(day)
        on_result(day, result)
        return False
