# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from .prayer_times import CalculationParams, PrayerTimes
from .prayers import Prayer
from .timeutil import local_now, wall_to_timestamp


@dataclass(frozen=True)
class UpcomingPrayer:
    prayer: Prayer
    when: datetime


class PrayerSchedule:
    def __init__(self, params: CalculationParams) -> None:
        self._params = params
        self.today: PrayerTimes = params.prayer_times()
        self._tomorrow: PrayerTimes | None = None
        self._tomorrow_unavailable = False

    @property
    def tz_name(self) -> str:
        return self._params.timezone

    def tomorrow(self) -> PrayerTimes | None:
        if self._tomorrow is None and not self._tomorrow_unavailable:
            try:
                self._tomorrow = self._params.prayer_times(self.today.date + timedelta(days=1))
            except ValueError:
                self._tomorrow_unavailable = True
        return self._tomorrow

    def next_prayer(self, now: datetime | None = None) -> UpcomingPrayer | None:
        if now is None:
            now = local_now(self.tz_name)
        upcoming = self.today.next_prayer(now)
        if upcoming is not None:
            return UpcomingPrayer(*upcoming)
        tomorrow = self.tomorrow()
        if tomorrow is None:
            return None
        return UpcomingPrayer(Prayer.FAJR, tomorrow.fajr)

    def seconds_until(self, moment: datetime, now_ts: float | None = None) -> int:
        if now_ts is None:
            now_ts = time.time()
        return max(0, int(wall_to_timestamp(moment, self.tz_name) - now_ts))
