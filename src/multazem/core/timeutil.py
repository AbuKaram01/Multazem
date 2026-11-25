# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Time-zone aware helpers shared by the calculation, scheduling and UI code.

Prayer times are calculated in the *configured location's* time zone and stored as naive
``datetime`` objects ("wall clock" times). Comparing them with the machine's clock only
works when both are converted to absolute timestamps first, which is what these helpers
are for.
"""

from __future__ import annotations

import zoneinfo
from datetime import datetime

from ..i18n import LocalizedError

DEFAULT_TIMEZONE = "Africa/Cairo"

# Unknown key, malformed key (absolute path, "..", ...), or a tz database that cannot be read.
_ZONE_LOOKUP_ERRORS = (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError)


def is_valid_timezone(name: object) -> bool:
    """Returns whether ``name`` is a non-empty string naming a time zone that can be loaded."""
    if not isinstance(name, str) or not name.strip():
        return False
    try:
        zoneinfo.ZoneInfo(name)
    except _ZONE_LOOKUP_ERRORS:
        return False
    return True


def zone_for(tz_name: str) -> zoneinfo.ZoneInfo:
    """Resolves an IANA time-zone name.

    Raises:
        LocalizedError: if the name is unknown, malformed or the time-zone database cannot be read.
    """
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except _ZONE_LOOKUP_ERRORS as error:
        raise LocalizedError("error.timezone_unknown", timezone=tz_name) from error


def local_now(tz_name: str) -> datetime:
    """Returns the current wall-clock time at the *configured location* (naive, like prayer times).

    Comparing prayer times with ``datetime.now()`` (the machine's zone) produced
    notifications at the wrong moment whenever the machine's zone differed from the
    configured city's zone (travelling, or a location set manually or via IP lookup).
    """
    return datetime.now(zone_for(tz_name)).replace(tzinfo=None)


def wall_to_timestamp(moment: datetime, tz_name: str) -> float:
    """Converts a naive wall-clock time at the location to an absolute Unix timestamp.

    This keeps "time remaining" correct even when a daylight-saving change falls
    between now and the target time.
    """
    return moment.replace(tzinfo=zone_for(tz_name)).timestamp()
