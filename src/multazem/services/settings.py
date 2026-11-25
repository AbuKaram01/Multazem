# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""User settings: location, calculation method, notification and display preferences.

Settings live in a local JSON file under ``$XDG_CONFIG_HOME`` (no network involved). The
GUI and the background service are separate processes that share the file, so the class
supports atomic saves, change detection (:meth:`Settings.reload_if_changed`) and change
listeners.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..core.calculation import ASR_SHADOW_STANDARD, VALID_ASR_SHADOWS, CalculationMethod
from ..core.coordinates import MAX_LATITUDE, MAX_LONGITUDE
from ..core.prayer_times import CalculationParams
from ..core.prayers import Prayer
from ..core.timeutil import is_valid_timezone
from ..i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, normalize_language
from ..logs import get_logger
from .atomic_json import backup_corrupt_file, write_json_atomic
from .paths import settings_file

logger = get_logger("settings")

# The defaults double as the schema: a saved value is accepted only if it has the type of its default.
DEFAULTS: dict[str, Any] = {
    "latitude": 30.0444,
    "longitude": 31.2357,
    "timezone_name": "Africa/Cairo",
    "city_name": "Cairo",
    "language": DEFAULT_LANGUAGE,
    "calculation_method": CalculationMethod.EGYPTIAN.name,
    "asr_shadow": ASR_SHADOW_STANDARD,
    # One switch per timetable entry (the five prayers and sunrise). It controls both the entry's own
    # notification and its reminder. On Fridays the Dhuhr switch governs the Friday (Jumu'ah) prayer,
    # which takes the same slot. Everything is on by default.
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
    # Optional and off by default to preserve the "fully offline" promise. When enabled, the official
    # Hijri date announced by Dar al-Ifta al-Misriyyah is fetched instead of the approximate local
    # calculation (see services/hijri_sync.py).
    "sync_hijri_online": False,
}

# Timetable entry -> settings key of its notification switch.
PRAYER_NOTIFY_KEYS: dict[Prayer, str] = {prayer: f"notify_{prayer.value}" for prayer in Prayer}

MIN_REMINDER_MINUTES = 1
MAX_REMINDER_MINUTES = 1440

ChangeListener = Callable[[str], None]
_FileStamp = tuple[int, int, int]


def _is_finite_number(value: Any) -> bool:
    """Returns whether ``value`` is a real, finite number.

    Not a bool, not NaN/Infinity (Python's JSON accepts both), and not an integer so
    large it cannot be converted to ``float``.
    """
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
    """Returns whether ``value`` is acceptable for the setting ``key``.

    The type must match the key's default; a few keys have an extra rule (see ``_EXTRA_VALIDATORS``).
    """
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
    """Returns a read/write property for a boolean setting."""
    return property(lambda self: bool(self.get(key)), lambda self, value: self.set(key, value))


class Settings:
    """Persistent, validated application settings.

    Values are read through typed properties that always return something usable, even when the
    file holds garbage; the raw values are available through :meth:`get` and :meth:`set`.
    Every real change is saved immediately and announced to the listeners.

    Args:
        path: The settings file; defaults to ``settings.json`` in the configuration directory.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._file = Path(path) if path else settings_file()
        self._data: dict[str, Any] = {}
        # Fingerprint (mtime / size / inode) of the file as of our last read or write. reload_if_changed()
        # compares it to detect edits made by another process.
        self._stamp: _FileStamp | None = None
        # Callbacks invoked after every real change, so the UI can refresh immediately (settings dialog,
        # bell buttons, location detection, or another process).
        self._listeners: list[ChangeListener] = []
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            # This used to crash the whole app at start-up (read-only settings directory, or a regular file
            # with the same name). Carry on with in-memory settings.
            logger.warning("Could not create the settings directory: %s", error)
        self._load()

    def _stat_stamp(self) -> _FileStamp | None:
        """Returns the file's (modification time, size, inode), or ``None`` if it cannot be read."""
        try:
            info = self._file.stat()
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size, info.st_ino)

    @staticmethod
    def _parse_settings_object(raw: bytes) -> dict:
        """Decodes JSON bytes and requires an object at the top level.

        Raises:
            ValueError: if the content is not valid JSON or not an object.
        """
        saved = json.loads(raw)
        if not isinstance(saved, dict):
            raise ValueError("the file content is not a JSON object")
        return saved

    def _load(self) -> None:
        """Loads the file, creating it with defaults when it does not exist.

        An unreadable file is left alone (defaults are used in memory only); a corrupt one is moved
        aside as ``.corrupt`` and replaced by the defaults.
        """
        try:
            raw = self._file.read_bytes()
        except FileNotFoundError:
            self._data = dict(DEFAULTS)
            self._save()
            return
        except OSError as error:
            # The file exists but cannot be read (permissions, transient I/O error). It used to be overwritten
            # with defaults, destroying the user's settings; now the defaults live in memory only.
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
        """Overlays saved values on :data:`DEFAULTS`, dropping anything invalid.

        Unknown keys are ignored. Values with the wrong type, non-finite numbers and
        unknown time zones fall back to their defaults.

        Returns:
            ``(merged settings, keys whose saved value was rejected)``.
        """
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
        """Writes the settings atomically; a failure is logged and the in-memory values are kept."""
        try:
            write_json_atomic(self._file, self._data)
            self._stamp = self._stat_stamp()
        except OSError as error:
            logger.warning("Failed to save: %s", error)

    def reload_if_changed(self) -> bool:
        """Re-reads the file if another process changed it since our last read or write.

        Returns ``True`` if the values actually changed, in which case the listeners are called with
        the key ``"*"``. A corrupt new file is ignored: we keep the in-memory settings instead of
        crashing or resetting to defaults.
        """
        stamp = self._stat_stamp()
        if stamp is None or stamp == self._stamp:
            return False
        # Remember the stamp even if reading fails, so we do not retry the same broken file on every call.
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
        """Registers ``listener(key)``, called after every change.

        The key is the name of the changed setting, or ``"*"`` when another process changed the file.
        """
        self._listeners.append(listener)

    def _notify_listeners(self, key: str) -> None:
        """Calls every listener; one that raises is logged and does not stop the others."""
        for listener in list(self._listeners):
            try:
                listener(key)
            except Exception as error:  # noqa: BLE001 - one faulty listener must not stop the others
                logger.error("Error in a change listener: %r", error)

    def get(self, key: str) -> Any:
        """Returns the raw value of ``key``, or its default when unset."""
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        """Stores ``value`` under ``key``, saves the file and notifies the listeners.

        Does nothing when the stored value is already identical (same type and value).
        """
        current = self._data.get(key)
        if key in self._data and type(current) is type(value) and current == value:
            return
        self._data[key] = value
        self._save()
        self._notify_listeners(key)

    def _finite_float(self, key: str) -> float:
        """Returns the setting as a float, or the default when it is not a finite number."""
        value = self.get(key)
        return float(value) if _is_finite_number(value) else DEFAULTS[key]

    def _finite_int(self, key: str) -> int:
        """Returns the setting as an int, or the default when it is not a finite number."""
        value = self.get(key)
        return int(value) if _is_finite_number(value) else DEFAULTS[key]

    @property
    def latitude(self) -> float:
        """Latitude in degrees, always within -90 to 90."""
        # Always a geographically valid value, even if the file holds an out-of-range number (a bad manual
        # edit, say). adhanpy happily computes times for any number, so without this clamp the user could
        # get completely wrong prayer times with no warning at all.
        return max(-MAX_LATITUDE, min(MAX_LATITUDE, self._finite_float("latitude")))

    @latitude.setter
    def latitude(self, value: float) -> None:
        self.set("latitude", value)

    @property
    def longitude(self) -> float:
        """Longitude in degrees, always within -180 to 180."""
        return max(-MAX_LONGITUDE, min(MAX_LONGITUDE, self._finite_float("longitude")))

    @longitude.setter
    def longitude(self, value: float) -> None:
        self.set("longitude", value)

    @property
    def timezone_name(self) -> str:
        """IANA name of the location's time zone."""
        return str(self.get("timezone_name"))

    @timezone_name.setter
    def timezone_name(self, value: str) -> None:
        self.set("timezone_name", value)

    @property
    def city_name(self) -> str:
        """Name of the chosen location, as it was stored when the location was picked."""
        return str(self.get("city_name"))

    @city_name.setter
    def city_name(self, value: str) -> None:
        self.set("city_name", value)

    @property
    def language(self) -> str:
        """UI language code; an unsupported stored value reads as the default language."""
        return normalize_language(self.get("language"))

    @language.setter
    def language(self, value: str) -> None:
        self.set("language", value)

    @property
    def calculation_method(self) -> CalculationMethod:
        """The calculation authority; an unknown stored name reads as the Egyptian method."""
        try:
            return CalculationMethod[self.get("calculation_method")]
        except KeyError:
            return CalculationMethod.EGYPTIAN

    @calculation_method.setter
    def calculation_method(self, value: CalculationMethod) -> None:
        self.set("calculation_method", value.name)

    @property
    def asr_shadow(self) -> int:
        """The Asr shadow length (``ASR_SHADOW_STANDARD`` or ``ASR_SHADOW_HANAFI``); invalid values read as standard."""
        value = self._finite_int("asr_shadow")
        return value if value in VALID_ASR_SHADOWS else ASR_SHADOW_STANDARD

    @asr_shadow.setter
    def asr_shadow(self, value: int) -> None:
        self.set("asr_shadow", value)

    @property
    def calculation_params(self) -> CalculationParams:
        """Everything the prayer-time calculation needs, as one value object."""
        return CalculationParams(
            latitude=self.latitude,
            longitude=self.longitude,
            timezone=self.timezone_name,
            method=self.calculation_method,
            asr_shadow=self.asr_shadow,
        )

    @property
    def reminder_minutes(self) -> int:
        """How many minutes before a prayer the reminder fires, limited to 1-1440."""
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
        """Returns whether this entry's notification and reminder are on."""
        return bool(self.get(PRAYER_NOTIFY_KEYS[prayer]))

    def set_prayer_enabled(self, prayer: Prayer, enabled: bool) -> None:
        """Turns the notification and reminder of one timetable entry on or off."""
        self.set(PRAYER_NOTIFY_KEYS[prayer], bool(enabled))
