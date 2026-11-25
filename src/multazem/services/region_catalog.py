# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The list of regions offered offline: the built-in cities plus the user's own.

Custom regions are persisted in a small JSON file (``regions.json`` next to the settings),
so a place added once stays available, without any network access, across restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..core.regions import (
    Region,
    RegionValidationError,
    build_region,
    build_region_from_text,
    builtin_regions,
    normalize_name,
    sort_key,
)
from ..i18n import DEFAULT_LANGUAGE, LocalizedError
from ..logs import get_logger
from .atomic_json import backup_corrupt_file, write_json_atomic
from .paths import custom_regions_file

_FORMAT_VERSION = 1

logger = get_logger("regions")


class RegionCatalog:
    """Built-in regions plus persisted, user-defined ones.

    Args:
        path: The JSON file holding the custom regions; defaults to the one in the configuration directory.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else custom_regions_file()
        self._builtin = builtin_regions()
        self._custom: list[Region] = []
        self._load_custom_regions()

    @property
    def custom_regions(self) -> tuple[Region, ...]:
        """The regions the user added, oldest first."""
        return tuple(self._custom)

    def regions(self, language: str = DEFAULT_LANGUAGE) -> list[Region]:
        """Returns the regions in picker order.

        The user's own come first (oldest first), then the built-in ones sorted by their name in
        ``language`` (ignoring the leading article).
        """
        builtin = sorted(self._builtin, key=lambda r: sort_key(r.name(language), language))
        return [*self._custom, *builtin]

    def find_by_name(self, name: str) -> Region | None:
        """Looks a region up by its name in *any* language (case-insensitive).

        Spellings shown by earlier versions (see ``Region.aliases``) match too, so a city
        saved in the settings under an old name is still recognised.
        """
        wanted = normalize_name(name)
        for region in (*self._custom, *self._builtin):
            if any(normalize_name(candidate) == wanted for candidate in region.lookup_names()):
                return region
        return None

    def display_name(self, stored_name: str, language: str) -> str:
        """Returns a stored city name in ``language`` when it is a known region, otherwise unchanged.

        The settings file keeps whatever name was current when the location was chosen
        (for example the Arabic one). Resolving it here lets the main window follow the
        language selector instead of staying stuck in the old language.
        """
        region = self.find_by_name(stored_name)
        return region.name(language) if region else stored_name

    def add(self, name: str, latitude_text: str, longitude_text: str, timezone: str) -> Region:
        """Validates, persists and returns a new custom region.

        Args:
            name: Name to show for the region.
            latitude_text: Latitude as typed by the user.
            longitude_text: Longitude as typed by the user.
            timezone: IANA time-zone name.

        Raises:
            RegionValidationError: an input is invalid (the error names the field).
            LocalizedError: the region could not be saved to disk; nothing is added in
                that case, so the UI never claims a region is stored when it is not.
        """
        region = build_region_from_text(name, latitude_text, longitude_text, timezone, self._taken_names())
        self._custom.append(region)
        try:
            self._save_custom_regions()
        except OSError as error:
            self._custom.pop()
            raise LocalizedError("region.error.save_failed", detail=str(error)) from error
        return region

    def _taken_names(self) -> list[str]:
        """Returns every name and alias in use, built-in and custom, for duplicate detection."""
        return [name for region in (*self._builtin, *self._custom) for name in region.lookup_names()]

    def _save_custom_regions(self) -> None:
        """Writes the custom regions to disk atomically.

        Raises:
            OSError: if the file cannot be written.
        """
        payload = {
            "version": _FORMAT_VERSION,
            "regions": [
                {
                    "name": region.name(),
                    "latitude": region.latitude,
                    "longitude": region.longitude,
                    "timezone": region.timezone,
                }
                for region in self._custom
            ],
        }
        write_json_atomic(self._path, payload)

    def _load_custom_regions(self) -> None:
        """Reads the persisted regions, skipping anything invalid instead of failing."""
        entries = self._read_entries()
        taken = self._taken_names()
        for entry in entries:
            try:
                region = self._region_from_entry(entry, taken)
            except (RegionValidationError, KeyError, TypeError) as error:
                logger.warning("Skipping an invalid custom region: %r", error)
                continue
            self._custom.append(region)
            taken.extend(region.all_names())

    def _read_entries(self) -> list[Any]:
        """Returns the raw region entries of the file; a missing, unreadable or corrupt file yields none.

        A corrupt file is moved aside with a ``.corrupt`` extension.
        """
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return []
        except OSError as error:
            logger.warning("Could not read the custom regions file: %s", error)
            return []

        try:
            return self._parse_entries(raw)
        except ValueError as error:
            backup_corrupt_file(self._path)
            logger.warning(
                "The custom regions file is corrupt; starting with an empty "
                "list (a copy was kept with a .corrupt extension): %s",
                error,
            )
            return []

    @staticmethod
    def _parse_entries(raw: bytes) -> list[Any]:
        """Decodes the file's JSON and returns its list of region entries.

        Raises:
            ValueError: if the document is not valid JSON or has no list of regions.
        """
        document = json.loads(raw)
        if not isinstance(document, dict) or not isinstance(document.get("regions"), list):
            raise ValueError("the file does not contain a list of regions")
        return document["regions"]

    @staticmethod
    def _region_from_entry(entry: Any, taken_names: list[str]) -> Region:
        """Builds a region from one stored entry, applying the same validation as user input.

        Raises:
            TypeError: if the entry or its name and time zone have the wrong type.
            KeyError: if a required field is missing.
            RegionValidationError: if a value is invalid or the name is already taken.
        """
        if not isinstance(entry, dict):
            raise TypeError("region entry is not an object")
        name = entry["name"]
        timezone = entry["timezone"]
        if not isinstance(name, str) or not isinstance(timezone, str):
            raise TypeError("name and timezone must be strings")
        return build_region(name, entry["latitude"], entry["longitude"], timezone, taken_names)
