# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Gregorian -> Hijri conversion (tabular algorithm) and parsing of official dates.

The real Hijri calendar is based on actual crescent sightings, and no purely arithmetic
formula can predict it with 100% accuracy (a one-day difference appears occasionally,
mostly around the start of a month). :func:`to_hijri` is therefore an *estimate* based
on the tabular Islamic calendar. It works fully offline and is always the default and the
fallback. The optional online synchronisation (``services.hijri_sync``) fetches the
officially announced date instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from ..i18n import tr

_MONTHS_IN_YEAR = 12


@dataclass(frozen=True, order=True)
class HijriDate:
    """A Hijri calendar date.

    The field order makes instances sort chronologically.

    Attributes:
        year: Hijri year (AH).
        month: Month number, 1 (Muharram) to 12 (Dhu al-Hijjah).
        day: Day of the month, 1 to 30.
    """

    year: int
    month: int
    day: int

    def format(self, language: str | None = None) -> str:
        """Formats the date for display, such as ``26 Rabi' al-Thani 1448 AH``.

        Args:
            language: Language code of the month name; ``None`` uses the current UI language.
        """
        return tr(
            "hijri.format",
            language=language,
            day=self.day,
            month=tr(f"hijri.month.{self.month}", language=language),
            year=self.year,
        )


def _gregorian_to_julian_day(year: int, month: int, day: int) -> int:
    """Returns the Julian day number of a Gregorian calendar date."""
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
    """Converts a Julian day number to ``(year, month, day)`` of the tabular Hijri calendar.

    The tabular calendar repeats a 30-year cycle of 10,631 days with eleven leap years.
    """
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
    """Estimates the Hijri date of a Gregorian day (offline, always available)."""
    year, month, hijri_day = _julian_day_to_hijri(_gregorian_to_julian_day(day.year, day.month, day.day))
    return HijriDate(year=year, month=month, day=hijri_day)


# The official source (Dar al-Ifta al-Misriyyah) publishes the date in Arabic, so the Arabic month names
# are needed to read it. They come from the same catalog the UI uses to keep a single source of truth.
_ARABIC_MONTH_NUMBERS = {tr(f"hijri.month.{number}", language="ar"): number for number in range(1, _MONTHS_IN_YEAR + 1)}
_OFFICIAL_DATE_PATTERN = re.compile(r"(\d{1,2})\s+(" + "|".join(_ARABIC_MONTH_NUMBERS) + r")\s+(\d{3,4})\s*ه")


def parse_official_hijri(page_text: str) -> HijriDate | None:
    """Extracts the first Arabic-script Hijri date from text.

    The expected shape is "day, Arabic month name, year, AH", the way the official source writes it.

    Args:
        page_text: Text of the page that announces the official date.

    Returns:
        The parsed date, or ``None`` when the text contains no date in that form.
    """
    match = _OFFICIAL_DATE_PATTERN.search(page_text)
    if match is None:
        return None
    day, month_name, year = match.groups()
    return HijriDate(year=int(year), month=_ARABIC_MONTH_NUMBERS[month_name], day=int(day))
