# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""A day's timetable plus the "what is coming next" logic the main window needs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from .prayer_times import CalculationParams, PrayerTimes
from .prayers import Prayer
from .timeutil import local_now, wall_to_timestamp


@dataclass(frozen=True)
class UpcomingPrayer:
    """The next prayer and when it starts (naive wall-clock time at the location)."""

    prayer: Prayer
    when: datetime


class PrayerSchedule:
    """Today's timetable and a lazily cached view of tomorrow's Fajr.

    After Isha there is no "next prayer" left today, so the countdown has to point at
    tomorrow's Fajr. That timetable is calculated once and cached; calculating it from
    scratch on every one-second UI tick was wasteful.

    A schedule is immutable in spirit: when the settings or the date change, build a new
    one instead of updating this one.

    Args:
        params: What determines the timetable. Today's timetable is calculated immediately.
    """

    def __init__(self, params: CalculationParams) -> None:
        self._params = params
        self.today: PrayerTimes = params.prayer_times()
        self._tomorrow: PrayerTimes | None = None
        self._tomorrow_unavailable = False

    @property
    def tz_name(self) -> str:
        """IANA name of the time zone the schedule is expressed in."""
        return self._params.timezone

    def tomorrow(self) -> PrayerTimes | None:
        """Returns tomorrow's timetable, or ``None`` if it cannot be calculated (polar regions)."""
        if self._tomorrow is None and not self._tomorrow_unavailable:
            try:
                self._tomorrow = self._params.prayer_times(self.today.date + timedelta(days=1))
            except ValueError:
                self._tomorrow_unavailable = True
        return self._tomorrow

    def next_prayer(self, now: datetime | None = None) -> UpcomingPrayer | None:
        """Returns the next prayer at ``now`` (default: the current time at the location).

        After Isha this is tomorrow's Fajr, or ``None`` when tomorrow cannot be calculated.
        """
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
        """Returns the whole seconds from now until ``moment``, never negative.

        Uses absolute timestamps (not a subtraction of two naive times) so the result is
        right even when a daylight-saving change falls in between.

        Args:
            moment: Wall-clock time at the location.
            now_ts: The current Unix timestamp; defaults to the system clock.
        """
        if now_ts is None:
            now_ts = time.time()
        return max(0, int(wall_to_timestamp(moment, self.tz_name) - now_ts))
