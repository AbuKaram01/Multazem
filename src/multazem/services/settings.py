# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..core.calculation import ASR_SHADOW_STANDARD, VALID_ASR_SHADOWS, CalculationMethod
from ..core.prayer_times import CalculationParams
from ..core.prayers import Prayer
from ..core.timeutil import is_valid_timezone
from ..i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, normalize_language
from ..logs import get_logger
from .atomic_json import backup_corrupt_file, write_json_atomic
from .paths import settings_file

logger = get_logger("settings")

DEFAULTS: dict[str, Any] = {
    "latitude": 30.0444,
    "longitude": 31.2357,
    "timezone_name": "Africa/Cairo",
    "city_name": "Cairo",
    "language": DEFAULT_LANGUAGE,
    "calculation_method": CalculationMethod.EGYPTIAN.name,
    "asr_shadow": ASR_SHADOW_STANDARD,
    "notify_on_prayer": True,
    "notify_fajr": True,
    "notify_sunrise": True,
    "notify_dhuhr": True,
    "notify_asr": True,
    "notify_maghrib": True,
    "notify_isha": True,
    "reminder_minutes": 10,
    "reminder_enabled": True,
    "play_adhan": False,
    "show_hijri": True,
    "sync_hijri_online": False,
}

PRAYER_NOTIFY_KEYS: dict[Prayer, str] = {prayer: f"notify_{prayer.value}" for prayer in Prayer}

MIN_REMINDER_MINUTES = 1
MAX_REMINDER_MINUTES = 1440

ChangeListener = Callable[[str], None]
_FileStamp = tuple[int, int, int]


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


# Checks that apply on top of the type check, for the keys that need one.
_EXTRA_VALIDATORS: dict[str, Callable[[Any], bool]] = {
    "timezone_name": is_valid_timezone,
    "language": lambda value: value in SUPPORTED_LANGUAGES,
}


def _is_valid_value(key: str, value: Any) -> bool:
    default = DEFAULTS[key]
    if isinstance(default, bool):
        valid = isinstance(value, bool)
    elif isinstance(default, (int, float)):
        valid = _is_finite_number(value)
    else:
        valid = isinstance(value, type(default))
    extra_check = _EXTRA_VALIDATORS.get(key)
    return valid and (extra_check is None or extra_check(value))


def _flag(key: str) -> property:
    return property(lambda self: bool(self.get(key)), lambda self, value: self.set(key, value))


class Settings:
    def __init__(self, path: Path | None = None) -> None:
        self._file = Path(path) if path else settings_file()
        self._data: dict[str, Any] = {}
        self._stamp: _FileStamp | None = None
        self._listeners: list[ChangeListener] = []
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            logger.warning("Could not create the settings directory: %s", error)
        self._load()

    def _stat_stamp(self) -> _FileStamp | None:
        try:
            info = self._file.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size, info.st_ino)

    @staticmethod
    def _parse_settings_object(raw: bytes) -> dict:
        saved = json.loads(raw)
        if not isinstance(saved, dict):
            raise ValueError("the file content is not a JSON object")
        return saved

    def _load(self) -> None:
        try:
            raw = self._file.read_bytes()
        except FileNotFoundError:
            self._data = dict(DEFAULTS)
            self._save()
            return
        except OSError as error:
            logger.warning(
                "Could not read the settings file (using defaults for now and NOT overwriting it): %s", error
            )
            self._data = dict(DEFAULTS)
            return

        try:
            saved = self._parse_settings_object(raw)
        except ValueError as error:
            backup_corrupt_file(self._file)
            logger.warning(
                "The settings file is corrupt; resetting to defaults (a copy "
                "of the corrupt file was kept next to it with a .corrupt extension): %s",
                error,
            )
            self._data = dict(DEFAULTS)
            self._save()
            return

        self._data, rejected_keys = self._merge_validated(saved)
        for key in rejected_keys:
            logger.warning('Ignoring "%s" (invalid value); using the default instead', key)
        self._stamp = self._stat_stamp()

    @staticmethod
    def _merge_validated(saved: dict) -> tuple[dict, list[str]]:
        merged = dict(DEFAULTS)
        rejected_keys = []
        for key, value in saved.items():
            if key not in DEFAULTS:
                continue
            if _is_valid_value(key, value):
                merged[key] = value
            else:
                rejected_keys.append(key)
        return merged, rejected_keys

    def _save(self) -> None:
        try:
            write_json_atomic(self._file, self._data)
            self._stamp = self._stat_stamp()
        except OSError as error:
            logger.warning("Failed to save: %s", error)

    def reload_if_changed(self) -> bool:
        stamp = self._stat_stamp()
        if stamp is None or stamp == self._stamp:
            return False
        self._stamp = stamp
        try:
            saved = self._parse_settings_object(self._file.read_bytes())
        except (OSError, ValueError) as error:
            logger.warning("The settings file changed but is unreadable; keeping the current settings: %s", error)
            return False
        updated, _rejected_keys = self._merge_validated(saved)
        changed = updated != self._data
        self._data = updated
        if changed:
            self._notify_listeners("*")
        return changed

    def add_listener(self, listener: ChangeListener) -> None:
        self._listeners.append(listener)

    def _notify_listeners(self, key: str) -> None:
        for listener in list(self._listeners):
            try:
                listener(key)
            except Exception as error:
                logger.error("Error in a change listener: %r", error)

    def get(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        current = self._data.get(key)
        if key in self._data and type(current) is type(value) and current == value:
            return
        self._data[key] = value
        self._save()
        self._notify_listeners(key)

    def _finite_float(self, key: str) -> float:
        value = self.get(key)
        return float(value) if _is_finite_number(value) else DEFAULTS[key]

    def _finite_int(self, key: str) -> int:
        value = self.get(key)
        return int(value) if _is_finite_number(value) else DEFAULTS[key]

    @property
    def latitude(self) -> float:
        return max(-90.0, min(90.0, self._finite_float("latitude")))

    @latitude.setter
    def latitude(self, value: float) -> None:
        self.set("latitude", value)

    @property
    def longitude(self) -> float:
        return max(-180.0, min(180.0, self._finite_float("longitude")))

    @longitude.setter
    def longitude(self, value: float) -> None:
        self.set("longitude", value)

    @property
    def timezone_name(self) -> str:
        return str(self.get("timezone_name"))

    @timezone_name.setter
    def timezone_name(self, value: str) -> None:
        self.set("timezone_name", value)

    @property
    def city_name(self) -> str:
        return str(self.get("city_name"))

    @city_name.setter
    def city_name(self, value: str) -> None:
        self.set("city_name", value)

    @property
    def language(self) -> str:
        return normalize_language(self.get("language"))

    @language.setter
    def language(self, value: str) -> None:
        self.set("language", value)

    @property
    def calculation_method(self) -> CalculationMethod:
        try:
            return CalculationMethod[self.get("calculation_method")]
        except KeyError:
            return CalculationMethod.EGYPTIAN

    @calculation_method.setter
    def calculation_method(self, value: CalculationMethod) -> None:
        self.set("calculation_method", value.name)

    @property
    def asr_shadow(self) -> int:
        value = self._finite_int("asr_shadow")
        return value if value in VALID_ASR_SHADOWS else ASR_SHADOW_STANDARD

    @asr_shadow.setter
    def asr_shadow(self, value: int) -> None:
        self.set("asr_shadow", value)

    @property
    def calculation_params(self) -> CalculationParams:
        return CalculationParams(
            latitude=self.latitude,
            longitude=self.longitude,
            timezone=self.timezone_name,
            method=self.calculation_method,
            asr_shadow=self.asr_shadow,
        )

    @property
    def reminder_minutes(self) -> int:
        return max(MIN_REMINDER_MINUTES, min(MAX_REMINDER_MINUTES, self._finite_int("reminder_minutes")))

    @reminder_minutes.setter
    def reminder_minutes(self, value: int) -> None:
        self.set("reminder_minutes", value)

    notify_on_prayer = _flag("notify_on_prayer")
    reminder_enabled = _flag("reminder_enabled")
    play_adhan = _flag("play_adhan")
    show_hijri = _flag("show_hijri")
    sync_hijri_online = _flag("sync_hijri_online")

    def prayer_enabled(self, prayer: Prayer) -> bool:
        return bool(self.get(PRAYER_NOTIFY_KEYS[prayer]))

    def set_prayer_enabled(self, prayer: Prayer, enabled: bool) -> None:
        self.set(PRAYER_NOTIFY_KEYS[prayer], bool(enabled))
