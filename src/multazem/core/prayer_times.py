# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Prayer-time calculation on top of ``adhanpy``.

``adhanpy`` is a pure-Python port of the open-source batoulapps/Adhan library (formulae
from Jean Meeus' *Astronomical Algorithms*). Everything is computed locally; no network
access is involved.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from adhanpy.calculation import CalculationMethod as _AdhanMethod
from adhanpy.calculation.CalculationParameters import (
    CalculationParameters as _AdhanParams,
)
from adhanpy.calculation.HighLatitudeRule import HighLatitudeRule as _HighLatitudeRule
from adhanpy.calculation.Madhab import Madhab as _Madhab
from adhanpy.calculation.PrayerAdjustments import PrayerAdjustments as _Adjustments
from adhanpy.PrayerTimes import PrayerTimes as _AdhanPrayerTimes

from ..i18n import LocalizedError
from .calculation import ASR_SHADOW_HANAFI, ASR_SHADOW_STANDARD, CalculationMethod
from .coordinates import MAX_LATITUDE, MAX_LONGITUDE
from .prayers import Prayer
from .timeutil import DEFAULT_TIMEZONE, local_now, zone_for

_ADHAN_METHODS = {
    CalculationMethod.EGYPTIAN: _AdhanMethod.EGYPTIAN,
    CalculationMethod.MUSLIM_WORLD_LEAGUE: _AdhanMethod.MUSLIM_WORLD_LEAGUE,
    CalculationMethod.NORTH_AMERICA: _AdhanMethod.NORTH_AMERICA,
    CalculationMethod.UMM_AL_QURA: _AdhanMethod.UMM_AL_QURA,
    CalculationMethod.KARACHI: _AdhanMethod.KARACHI,
    CalculationMethod.KUWAIT: _AdhanMethod.KUWAIT,
    CalculationMethod.QATAR: _AdhanMethod.QATAR,
}

# Above this absolute latitude (most of Europe) adhanpy's default high-latitude rule ("middle of the
# night") gives Fajr and Isha the exact same time in summer, for example London on 21 June. The Adhan
# project recommends "one seventh of the night" there. Egypt, Saudi Arabia and the rest of the Arab
# world are all below it.
_HIGH_LATITUDE_THRESHOLD = 48


@dataclass
class PrayerTimes:
    """The timetable of a single day, as naive wall-clock times at the location.

    Attributes:
        fajr: Start of Fajr.
        sunrise: Sunrise. It ends the time of Fajr but is not itself a prayer.
        dhuhr: Start of Dhuhr (Jumu'ah on Fridays).
        asr: Start of Asr.
        maghrib: Start of Maghrib.
        isha: Start of Isha.
        date: The calendar day at the location that this timetable is for.
        tz_name: IANA name of the time zone the wall-clock times are expressed in.
    """

    fajr: datetime
    sunrise: datetime
    dhuhr: datetime
    asr: datetime
    maghrib: datetime
    isha: datetime
    date: date
    tz_name: str = "UTC"

    def as_dict(self) -> dict[Prayer, datetime]:
        """Returns the timetable in daily order (sunrise included)."""
        return {
            Prayer.FAJR: self.fajr,
            Prayer.SUNRISE: self.sunrise,
            Prayer.DHUHR: self.dhuhr,
            Prayer.ASR: self.asr,
            Prayer.MAGHRIB: self.maghrib,
            Prayer.ISHA: self.isha,
        }

    def next_prayer(self, now: datetime | None = None) -> tuple[Prayer, datetime] | None:
        """Returns the first prayer still ahead of ``now``, or ``None`` after Isha.

        Sunrise is skipped because it is not a prayer.

        Args:
            now: Wall-clock time at the location; defaults to the current time there.
        """
        if now is None:
            now = local_now(self.tz_name)
        now = now.replace(tzinfo=None)
        for prayer, moment in self.as_dict().items():
            if prayer.is_prayer and moment.replace(tzinfo=None) > now:
                return prayer, moment
        return None


@dataclass(frozen=True)
class CalculationParams:
    """Everything that determines the timetable of a given day.

    Attributes:
        latitude: Degrees north (negative for south).
        longitude: Degrees east (negative for west).
        timezone: IANA name of the location's time zone.
        method: The calculation authority.
        asr_shadow: ``ASR_SHADOW_STANDARD`` or ``ASR_SHADOW_HANAFI``.
    """

    latitude: float
    longitude: float
    timezone: str
    method: CalculationMethod = CalculationMethod.EGYPTIAN
    asr_shadow: int = ASR_SHADOW_STANDARD

    def prayer_times(self, day: date | None = None) -> PrayerTimes:
        """Calculates the timetable for ``day`` (default: today at the location)."""
        return calculate_prayer_times(
            self.latitude,
            self.longitude,
            self.timezone,
            day,
            self.method,
            self.asr_shadow,
        )


def calculate_prayer_times(
    lat: float,
    lon: float,
    tz_name: str = DEFAULT_TIMEZONE,
    target_date: date | None = None,
    method: CalculationMethod = CalculationMethod.EGYPTIAN,
    asr_shadow: int = ASR_SHADOW_STANDARD,
) -> PrayerTimes:
    """Calculates one day's timetable.

    Args:
        lat: Latitude in degrees, -90 to 90.
        lon: Longitude in degrees, -180 to 180.
        tz_name: IANA name of the location's time zone.
        target_date: The day to calculate; defaults to today at the location.
        method: The calculation authority.
        asr_shadow: ``ASR_SHADOW_STANDARD`` or ``ASR_SHADOW_HANAFI``.

    Returns:
        The timetable, with every time expressed as wall-clock time in ``tz_name``.

    Raises:
        LocalizedError: (a ``ValueError``) for an out-of-range coordinate, an unknown
            time zone, or a location where the sun does not rise or set on that day.
    """
    _require_valid_coordinates(lat, lon)
    zone = zone_for(tz_name)
    # "Today" at the location, not on the machine running the app.
    if target_date is None:
        target_date = datetime.now(zone).date()

    raw = _compute_with_adhan(lat, lon, target_date, zone, _build_adhan_parameters(lat, method, asr_shadow))
    moments = (raw.fajr, raw.sunrise, raw.dhuhr, raw.asr, raw.maghrib, raw.isha)
    if any(moment is None for moment in moments):
        raise LocalizedError("error.times_incomplete", latitude=f"{lat:.2f}", date=target_date)

    fajr, sunrise, dhuhr, asr, maghrib, isha = (moment.replace(tzinfo=None) for moment in moments)
    return PrayerTimes(
        fajr=fajr,
        sunrise=sunrise,
        dhuhr=dhuhr,
        asr=asr,
        maghrib=maghrib,
        isha=isha,
        date=target_date,
        tz_name=tz_name,
    )


def _require_valid_coordinates(lat: float, lon: float) -> None:
    """Raises ``LocalizedError`` unless both coordinates are within range (NaN is rejected too)."""
    if not abs(lat) <= MAX_LATITUDE:
        raise LocalizedError("error.latitude_out_of_range", latitude=lat)
    if not abs(lon) <= MAX_LONGITUDE:
        raise LocalizedError("error.longitude_out_of_range", longitude=lon)


def _compute_with_adhan(
    lat: float, lon: float, target_date: date, zone: ZoneInfo, parameters: _AdhanParams
) -> _AdhanPrayerTimes:
    """Runs ``adhanpy``, turning its bare ``RuntimeError`` into a ``LocalizedError``.

    ``adhanpy`` raises ``RuntimeError`` when the sun neither rises nor sets on the day (near the
    poles). Callers only expect ``ValueError``, so an uncaught one used to crash the app at start-up.
    """
    try:
        return _AdhanPrayerTimes((lat, lon), target_date, calculation_parameters=parameters, time_zone=zone)
    except RuntimeError as error:
        raise LocalizedError("error.sun_never_crosses", latitude=f"{lat:.2f}", date=target_date) from error


def _build_adhan_parameters(latitude: float, method: CalculationMethod, asr_shadow: int) -> _AdhanParams:
    """Builds the ``adhanpy`` parameters for a method, madhab and latitude.

    The only adjustment is Dhuhr -1 minute; see the comment inside for how that was calibrated.
    """
    params = _AdhanParams(method=_ADHAN_METHODS.get(method, _AdhanMethod.EGYPTIAN))
    if asr_shadow == ASR_SHADOW_HANAFI:
        params.madhab = _Madhab.HANAFI
    if abs(latitude) > _HIGH_LATITUDE_THRESHOLD:
        params.high_latitude_rule = _HighLatitudeRule.SEVENTH_OF_THE_NIGHT

    # Only Dhuhr is shifted, by -1 minute. adhanpy models EGYPTIAN as an approximation of the Egyptian
    # General Authority of Survey method; the authority does not publish its exact formulae, so a literal
    # match is impossible. Compared with the official esa.gov.eg table for six locations (Cairo,
    # Alexandria, Aswan, Saint Catherine, El Alamein, New Administrative Capital) on 2026-08-20:
    #   - Dhuhr: adhanpy is always one minute ahead, so -1 matches in all six cases.
    #   - Asr: matches in five of six without adjustment (Saint Catherine is one minute off, probably
    #     because of its altitude). An earlier version also shifted Asr, which moved it away from the
    #     official value.
    #   - Fajr, sunrise, Maghrib, Isha: identical apart from rounding noise.
    # With the other methods the same adjustment stays within a minute, inside the usual disagreement
    # between sources, but the calibration itself is specific to the Egyptian method.
    params.adjustments = _Adjustments(dhuhr=-1)
    return params
