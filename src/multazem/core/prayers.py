# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Entries of the daily prayer timetable."""

from __future__ import annotations

from datetime import date
from enum import Enum

#: ``datetime.date.weekday()`` value of Friday (Monday is 0).
FRIDAY = 4

_JUMUAH_LABEL_KEY = "prayer.jumuah"


class Prayer(Enum):
    """One row of the daily timetable.

    Sunrise is part of the timetable and can notify like any other row, but it is not a
    prayer: it is never "the next prayer" shown by the countdown.
    """

    FAJR = "fajr"
    SUNRISE = "sunrise"
    DHUHR = "dhuhr"
    ASR = "asr"
    MAGHRIB = "maghrib"
    ISHA = "isha"

    @property
    def label_key(self) -> str:
        """Translation key of the everyday display name (see :mod:`multazem.i18n`)."""
        return f"prayer.{self.value}"

    def label_key_on(self, day: date) -> str:
        """Translation key of the display name on a specific day.

        On Fridays the Dhuhr slot is the Friday (Jumu'ah) congregational prayer, so it is
        shown under that name instead. ``day`` must be the calendar date *at the
        configured location* (as in :attr:`PrayerTimes.date`), not the machine's date.
        """
        if self is Prayer.DHUHR and day.weekday() == FRIDAY:
            return _JUMUAH_LABEL_KEY
        return self.label_key

    @property
    def is_prayer(self) -> bool:
        """``False`` only for sunrise."""
        return self is not Prayer.SUNRISE


OBLIGATORY_PRAYERS: tuple[Prayer, ...] = tuple(p for p in Prayer if p.is_prayer)
