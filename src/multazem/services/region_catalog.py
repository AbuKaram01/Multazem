# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


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
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else custom_regions_file()
        self._builtin = builtin_regions()
        self._custom: list[Region] = []
        self._load_custom_regions()

    @property
    def custom_regions(self) -> tuple[Region, ...]:
        return tuple(self._custom)

    def regions(self, language: str = DEFAULT_LANGUAGE) -> list[Region]:
        builtin = sorted(self._builtin, key=lambda r: sort_key(r.name(language), language))
        return [*self._custom, *builtin]

    def find_by_name(self, name: str) -> Region | None:
        wanted = normalize_name(name)
        for region in (*self._custom, *self._builtin):
            if any(normalize_name(candidate) == wanted for candidate in region.lookup_names()):
                return region
        return None

    def display_name(self, stored_name: str, language: str) -> str:
        region = self.find_by_name(stored_name)
        return region.name(language) if region else stored_name

    def add(self, name: str, latitude_text: str, longitude_text: str, timezone: str) -> Region:
        region = build_region_from_text(name, latitude_text, longitude_text, timezone, self._taken_names())
        self._custom.append(region)
        try:
            self._save_custom_regions()
        except OSError as error:
            self._custom.pop()
            raise LocalizedError("region.error.save_failed", detail=str(error)) from error
        return region

    def _taken_names(self) -> list[str]:
        return [name for region in (*self._builtin, *self._custom) for name in region.lookup_names()]

    def _save_custom_regions(self) -> None:
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
        document = json.loads(raw)
        if not isinstance(document, dict) or not isinstance(document.get("regions"), list):
            raise ValueError("the file does not contain a list of regions")
        return document["regions"]

    @staticmethod
    def _region_from_entry(entry: Any, taken_names: list[str]) -> Region:
        if not isinstance(entry, dict):
            raise TypeError("region entry is not an object")
        name = entry["name"]
        timezone = entry["timezone"]
        if not isinstance(name, str) or not isinstance(timezone, str):
            raise TypeError("name and timezone must be strings")
        return build_region(name, entry["latitude"], entry["longitude"], timezone, taken_names)
