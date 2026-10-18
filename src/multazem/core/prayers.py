# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from datetime import date
from enum import Enum

#: ``datetime.date.weekday()`` value of Friday (Monday is 0).
FRIDAY = 4

_JUMUAH_LABEL_KEY = "prayer.jumuah"


class Prayer(Enum):
    FAJR = "fajr"
    SUNRISE = "sunrise"
    DHUHR = "dhuhr"
    ASR = "asr"
    MAGHRIB = "maghrib"
    ISHA = "isha"

    @property
    def label_key(self) -> str:
        return f"prayer.{self.value}"

    def label_key_on(self, day: date) -> str:
        if self is Prayer.DHUHR and day.weekday() == FRIDAY:
            return _JUMUAH_LABEL_KEY
        return self.label_key

    @property
    def is_prayer(self) -> bool:
        """``False`` only for sunrise."""
        return self is not Prayer.SUNRISE


OBLIGATORY_PRAYERS: tuple[Prayer, ...] = tuple(p for p in Prayer if p.is_prayer)
