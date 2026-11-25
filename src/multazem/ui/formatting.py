# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Formatting of values for display."""

from __future__ import annotations

from datetime import date

from ..i18n import tr

_SECONDS_PER_HOUR = 3600
_SECONDS_PER_MINUTE = 60


def format_weekday_and_date(day: date) -> str:
    """Formats a date as, for example, ``Thursday, 15 / 10 / 2026`` in the active language."""
    return tr(
        "window.date_format",
        weekday=tr(f"weekday.{day.weekday()}"),
        date=day.strftime("%d / %m / %Y"),
    )


def format_countdown(total_seconds: int) -> str:
    """Formats the time left until the next prayer as ``HH:MM:SS`` inside a localized sentence.

    Args:
        total_seconds: Whole seconds remaining; never negative.
    """
    hours, remainder = divmod(total_seconds, _SECONDS_PER_HOUR)
    minutes, seconds = divmod(remainder, _SECONDS_PER_MINUTE)
    return tr("window.countdown", hours=hours, minutes=minutes, seconds=seconds)
