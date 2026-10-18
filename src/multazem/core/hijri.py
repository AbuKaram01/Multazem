# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from ..i18n import tr

_MONTHS_IN_YEAR = 12


@dataclass(frozen=True, order=True)
class HijriDate:
    year: int
    month: int
    day: int

    def format(self, language: str | None = None) -> str:
        return tr(
            "hijri.format",
            language=language,
            day=self.day,
            month=tr(f"hijri.month.{self.month}", language=language),
            year=self.year,
        )


def _gregorian_to_julian_day(year: int, month: int, day: int) -> int:
    shift = (14 - month) // 12
    shifted_year = year + 4800 - shift
    shifted_month = month + 12 * shift - 3
    return (
        day
        + (153 * shifted_month + 2) // 5
        + 365 * shifted_year
        + shifted_year // 4
        - shifted_year // 100
        + shifted_year // 400
        - 32045
    )


def _julian_day_to_hijri(julian_day: int) -> tuple[int, int, int]:
    days = julian_day - 1948440 + 10632
    cycle = (days - 1) // 10631
    days = days - 10631 * cycle + 354
    year_in_cycle = ((10985 - days) // 5316) * ((50 * days) // 17719) + (days // 5670) * ((43 * days) // 15238)
    days = (
        days
        - ((30 - year_in_cycle) // 15) * ((17719 * year_in_cycle) // 50)
        - (year_in_cycle // 16) * ((15238 * year_in_cycle) // 43)
        + 29
    )
    year = 30 * cycle + year_in_cycle - 30
    month = (24 * days) // 709
    day = days - (709 * month) // 24
    return year, month, day


def to_hijri(day: date) -> HijriDate:
    year, month, hijri_day = _julian_day_to_hijri(_gregorian_to_julian_day(day.year, day.month, day.day))
    return HijriDate(year=year, month=month, day=hijri_day)


_ARABIC_MONTH_NUMBERS = {tr(f"hijri.month.{number}", language="ar"): number for number in range(1, _MONTHS_IN_YEAR + 1)}
_OFFICIAL_DATE_PATTERN = re.compile(r"(\d{1,2})\s+(" + "|".join(_ARABIC_MONTH_NUMBERS) + r")\s+(\d{3,4})\s*ه")


def parse_official_hijri(page_text: str) -> HijriDate | None:
    match = _OFFICIAL_DATE_PATTERN.search(page_text)
    if match is None:
        return None
    day, month_name, year = match.groups()
    return HijriDate(year=int(year), month=_ARABIC_MONTH_NUMBERS[month_name], day=int(day))
