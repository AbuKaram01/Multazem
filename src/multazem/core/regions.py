# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, LocalizedError
from .egypt_cities import EGYPT_CITIES, FORMER_ENGLISH_NAMES
from .timeutil import DEFAULT_TIMEZONE, is_valid_timezone

MAX_REGION_NAME_LENGTH = 60
MAX_LATITUDE = 90.0
MAX_LONGITUDE = 180.0


@dataclass(frozen=True)
class Region:
    names: Mapping[str, str]
    latitude: float
    longitude: float
    timezone: str
    is_custom: bool = False
    aliases: tuple[str, ...] = ()

    def name(self, language: str = DEFAULT_LANGUAGE) -> str:
        return self.names.get(language) or self.names.get(DEFAULT_LANGUAGE) or next(iter(self.names.values()))

    def all_names(self) -> tuple[str, ...]:
        return tuple(self.names.values())

    def lookup_names(self) -> tuple[str, ...]:
        return (*self.names.values(), *self.aliases)


def builtin_regions() -> list[Region]:
    return [
        Region(
            names={"ar": arabic_name, "en": english_name},
            latitude=latitude,
            longitude=longitude,
            timezone=DEFAULT_TIMEZONE,
            aliases=(FORMER_ENGLISH_NAMES[arabic_name],) if arabic_name in FORMER_ENGLISH_NAMES else (),
        )
        for arabic_name, english_name, latitude, longitude in EGYPT_CITIES
    ]


def normalize_name(name: str) -> str:
    return " ".join(name.split()).casefold()


_ENGLISH_ARTICLE = "el "
_ARABIC_ARTICLE = "ال"


def sort_key(name: str, language: str) -> str:
    key = normalize_name(name)
    if language == "ar":
        if key.startswith(_ARABIC_ARTICLE) and len(key) > len(_ARABIC_ARTICLE):
            return key[len(_ARABIC_ARTICLE) :]
    elif key.startswith(_ENGLISH_ARTICLE):
        return key[len(_ENGLISH_ARTICLE) :]
    return key


class RegionValidationError(LocalizedError):
    def __init__(self, field: str, reason: str, **params: object) -> None:
        self.field = field
        super().__init__(f"region.error.{field}_{reason}", **params)


_NUMBER_TRANSLATION = str.maketrans(
    {
        **{0x0660 + digit: str(digit) for digit in range(10)},  # Arabic-Indic digits
        **{0x06F0 + digit: str(digit) for digit in range(10)},  # Extended (Persian) digits
        0x066B: ".",  # Arabic decimal separator
        0x002C: ".",  # comma used as a decimal separator
        0x060C: ".",  # Arabic comma
        0x2212: "-",  # Unicode minus sign
    }
)
_DECIMAL_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)")


def parse_coordinate(raw: str, *, field: str, limit: float) -> float:
    text = raw.strip().translate(_NUMBER_TRANSLATION).replace("°", "").strip()
    if not _DECIMAL_NUMBER.fullmatch(text):
        raise RegionValidationError(field, "invalid")
    value = float(text)
    _require_coordinate_in_range(field, value, limit)
    return value


def _require_coordinate_in_range(field: str, value: float, limit: float) -> None:
    if not math.isfinite(value):
        raise RegionValidationError(field, "invalid")
    if abs(value) > limit:
        raise RegionValidationError(field, "range", limit=int(limit))


def build_region(
    name: str,
    latitude: float,
    longitude: float,
    timezone: str,
    taken_names: Iterable[str] = (),
) -> Region:
    clean_name = _validated_name(name, taken_names)

    for field, value, limit in (
        ("latitude", latitude, MAX_LATITUDE),
        ("longitude", longitude, MAX_LONGITUDE),
    ):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RegionValidationError(field, "invalid")
        _require_coordinate_in_range(field, value, limit)

    clean_timezone = timezone.strip()
    if not is_valid_timezone(clean_timezone):
        raise RegionValidationError("timezone", "invalid")

    return Region(
        names=dict.fromkeys(SUPPORTED_LANGUAGES, clean_name),
        latitude=float(latitude),
        longitude=float(longitude),
        timezone=clean_timezone,
        is_custom=True,
    )


def build_region_from_text(
    name: str,
    latitude_text: str,
    longitude_text: str,
    timezone: str,
    taken_names: Iterable[str] = (),
) -> Region:
    clean_name = _validated_name(name, taken_names)
    latitude = parse_coordinate(latitude_text, field="latitude", limit=MAX_LATITUDE)
    longitude = parse_coordinate(longitude_text, field="longitude", limit=MAX_LONGITUDE)
    return build_region(clean_name, latitude, longitude, timezone, taken_names)


def _validated_name(name: str, taken_names: Iterable[str]) -> str:
    clean_name = " ".join(name.split())
    if not clean_name:
        raise RegionValidationError("name", "required")
    if len(clean_name) > MAX_REGION_NAME_LENGTH:
        raise RegionValidationError("name", "too_long", max=MAX_REGION_NAME_LENGTH)
    if normalize_name(clean_name) in {normalize_name(taken) for taken in taken_names}:
        raise RegionValidationError("name", "exists", name=clean_name)
    return clean_name
