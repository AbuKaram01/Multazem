# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

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

_HIGH_LATITUDE_THRESHOLD = 48


@dataclass
class PrayerTimes:
    fajr: datetime
    sunrise: datetime
    dhuhr: datetime
    asr: datetime
    maghrib: datetime
    isha: datetime
    date: date
    tz_name: str = "UTC"

    def as_dict(self) -> dict[Prayer, datetime]:
        return {
            Prayer.FAJR: self.fajr,
            Prayer.SUNRISE: self.sunrise,
            Prayer.DHUHR: self.dhuhr,
            Prayer.ASR: self.asr,
            Prayer.MAGHRIB: self.maghrib,
            Prayer.ISHA: self.isha,
        }

    def next_prayer(self, now: datetime | None = None) -> tuple[Prayer, datetime] | None:
        if now is None:
            now = local_now(self.tz_name)
        now = now.replace(tzinfo=None)
        for prayer, moment in self.as_dict().items():
            if prayer.is_prayer and moment.replace(tzinfo=None) > now:
                return prayer, moment
        return None


@dataclass(frozen=True)
class CalculationParams:
    latitude: float
    longitude: float
    timezone: str
    method: CalculationMethod = CalculationMethod.EGYPTIAN
    asr_shadow: int = ASR_SHADOW_STANDARD

    def prayer_times(self, day: date | None = None) -> PrayerTimes:
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
    _require_valid_coordinates(lat, lon)
    zone = zone_for(tz_name)
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
    if not (-90 <= lat <= 90):
        raise LocalizedError("error.latitude_out_of_range", latitude=lat)
    if not (-180 <= lon <= 180):
        raise LocalizedError("error.longitude_out_of_range", longitude=lon)


def _compute_with_adhan(
    lat: float, lon: float, target_date: date, zone: ZoneInfo, parameters: _AdhanParams
) -> _AdhanPrayerTimes:
    try:
        return _AdhanPrayerTimes((lat, lon), target_date, calculation_parameters=parameters, time_zone=zone)
    except RuntimeError as error:
        raise LocalizedError("error.sun_never_crosses", latitude=f"{lat:.2f}", date=target_date) from error


def _build_adhan_parameters(latitude: float, method: CalculationMethod, asr_shadow: int) -> _AdhanParams:
    params = _AdhanParams(method=_ADHAN_METHODS.get(method, _AdhanMethod.EGYPTIAN))
    if asr_shadow == ASR_SHADOW_HANAFI:
        params.madhab = _Madhab.HANAFI
    if abs(latitude) > _HIGH_LATITUDE_THRESHOLD:
        params.high_latitude_rule = _HighLatitudeRule.SEVENTH_OF_THE_NIGHT

    params.adjustments = _Adjustments(dhuhr=-1)
    return params
