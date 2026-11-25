# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Regions (named places with coordinates) and validation of user-entered ones.

A *region* is what the location picker offers: a place name plus the latitude, longitude
and time zone needed to calculate prayer times offline. The built-in table covers Egypt;
users can add their own regions at runtime (see ``services.region_catalog``).
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ..i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, LocalizedError
from .coordinates import MAX_LATITUDE, MAX_LONGITUDE
from .egypt_cities import EGYPT_CITIES, FORMER_ENGLISH_NAMES
from .timeutil import DEFAULT_TIMEZONE, is_valid_timezone

MAX_REGION_NAME_LENGTH = 60


@dataclass(frozen=True)
class Region:
    """A named place.

    ``names`` maps a language code to the name in that language. A place name is a proper
    name: the English one is the Arabic name written in Latin letters (transliterated),
    never a translation. A region the user adds keeps the single name that was typed.

    ``aliases`` are other spellings that must still be recognised when a stored name is
    looked up (names shown by an earlier version). They are never displayed.

    Attributes:
        names: Display name per language code.
        latitude: Degrees north (negative for south).
        longitude: Degrees east (negative for west).
        timezone: IANA name of the time zone.
        is_custom: ``True`` for a region the user added, ``False`` for a built-in one.
        aliases: Additional spellings that identify the region when looked up by name.
    """

    names: Mapping[str, str]
    latitude: float
    longitude: float
    timezone: str
    is_custom: bool = False
    aliases: tuple[str, ...] = ()

    def name(self, language: str = DEFAULT_LANGUAGE) -> str:
        """Returns the name in ``language``, falling back to English and then to any available name."""
        return self.names.get(language) or self.names.get(DEFAULT_LANGUAGE) or next(iter(self.names.values()))

    def all_names(self) -> tuple[str, ...]:
        """Returns the displayed names of every language."""
        return tuple(self.names.values())

    def lookup_names(self) -> tuple[str, ...]:
        """Returns every spelling that identifies this region: its names and its aliases."""
        return (*self.names.values(), *self.aliases)


def builtin_regions() -> list[Region]:
    """Returns the bundled Egyptian cities as regions (Arabic name and its transliteration)."""
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
    """Returns the canonical form used to compare names: collapsed whitespace, case-insensitive."""
    return " ".join(name.split()).casefold()


_ENGLISH_ARTICLE = "el "
_ARABIC_ARTICLE = "ال"


def sort_key(name: str, language: str) -> str:
    """Returns the alphabetical position of a name, ignoring its leading article.

    Nearly every Egyptian city starts with the article (``El Mansoura``, المنصورة), which
    would pile up half of the list under one letter. Dictionaries file them under the
    first letter of the real name (Mansoura), and so does the picker.

    Args:
        name: The name to sort.
        language: ``"ar"`` strips the Arabic article, any other value the English ``El``.
    """
    key = normalize_name(name)
    if language == "ar":
        if key.startswith(_ARABIC_ARTICLE) and len(key) > len(_ARABIC_ARTICLE):
            return key[len(_ARABIC_ARTICLE) :]
    elif key.startswith(_ENGLISH_ARTICLE):
        return key[len(_ENGLISH_ARTICLE) :]
    return key


class RegionValidationError(LocalizedError):
    """A region form field is invalid. ``field`` names the offending input.

    ``field`` is one of ``"name"``, ``"latitude"``, ``"longitude"`` or ``"timezone"``,
    so a UI can highlight the right widget.

    Args:
        field: The invalid input.
        reason: Short reason code; ``"{field}_{reason}"`` completes the message key.
        **params: Values substituted into the message.
    """

    def __init__(self, field: str, reason: str, **params: object) -> None:
        self.field = field
        super().__init__(f"region.error.{field}_{reason}", **params)


# Users of the Arabic UI naturally type Arabic-Indic digits and the Arabic decimal separator, so those are
# accepted alongside the usual ASCII forms.
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
    """Parses a latitude or longitude typed by a user.

    Arabic-Indic digits, the Arabic decimal separator and a trailing degree sign are accepted.

    Args:
        raw: The text the user typed.
        field: ``"latitude"`` or ``"longitude"``, used to report which input is wrong.
        limit: Largest accepted absolute value in degrees.

    Returns:
        The coordinate in decimal degrees.

    Raises:
        RegionValidationError: if the text is not a plain decimal number (so ``nan``,
            ``inf``, exponents and thousands separators are rejected) or if its absolute
            value exceeds ``limit``.
    """
    text = raw.strip().translate(_NUMBER_TRANSLATION).replace("°", "").strip()
    if not _DECIMAL_NUMBER.fullmatch(text):
        raise RegionValidationError(field, "invalid")
    value = float(text)
    _require_coordinate_in_range(field, value, limit)
    return value


def _require_coordinate_in_range(field: str, value: float, limit: float) -> None:
    """Raises ``RegionValidationError`` unless ``value`` is finite and within ``limit`` degrees."""
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
    """Validates typed values and builds a custom region.

    Args:
        name: The name to show for the region, in every language.
        latitude: Degrees north.
        longitude: Degrees east.
        timezone: IANA name of the time zone.
        taken_names: Names already used by other regions; a custom name may not collide
            with any of them (in any language), because regions are looked up by name.

    Raises:
        RegionValidationError: for the first invalid field.
    """
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

    # A custom region has a single user-typed name that is shown in every language.
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
    """Like :func:`build_region`, but parses coordinates from raw form text first.

    Fields are validated in form order (name, latitude, longitude, time zone) so that the
    first error reported is the first one the user sees on screen.
    """
    clean_name = _validated_name(name, taken_names)
    latitude = parse_coordinate(latitude_text, field="latitude", limit=MAX_LATITUDE)
    longitude = parse_coordinate(longitude_text, field="longitude", limit=MAX_LONGITUDE)
    return build_region(clean_name, latitude, longitude, timezone, taken_names)


def _validated_name(name: str, taken_names: Iterable[str]) -> str:
    """Returns the whitespace-normalised name or raises for an empty, too long or duplicate one."""
    clean_name = " ".join(name.split())
    if not clean_name:
        raise RegionValidationError("name", "required")
    if len(clean_name) > MAX_REGION_NAME_LENGTH:
        raise RegionValidationError("name", "too_long", max=MAX_REGION_NAME_LENGTH)
    if normalize_name(clean_name) in {normalize_name(taken) for taken in taken_names}:
        raise RegionValidationError("name", "exists", name=clean_name)
    return clean_name
