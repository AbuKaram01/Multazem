# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

import zoneinfo
from datetime import datetime

from ..i18n import LocalizedError

DEFAULT_TIMEZONE = "Africa/Cairo"

# Unknown key, malformed key (absolute path, "..", ...), or a tz database that cannot be read.
_ZONE_LOOKUP_ERRORS = (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError)


def is_valid_timezone(name: object) -> bool:
    if not isinstance(name, str) or not name.strip():
        return False
    try:
        zoneinfo.ZoneInfo(name)
    except _ZONE_LOOKUP_ERRORS:
        return False
    return True


def zone_for(tz_name: str) -> zoneinfo.ZoneInfo:
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except _ZONE_LOOKUP_ERRORS as error:
        raise LocalizedError("error.timezone_unknown", timezone=tz_name) from error


def local_now(tz_name: str) -> datetime:
    return datetime.now(zone_for(tz_name)).replace(tzinfo=None)


def wall_to_timestamp(moment: datetime, tz_name: str) -> float:
    return moment.replace(tzinfo=zone_for(tz_name)).timestamp()
