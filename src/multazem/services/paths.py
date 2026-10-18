# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Locations of the application's files on disk.

On Linux they follow the XDG Base Directory specification. On Windows the settings live in the roaming profile
(``%APPDATA%``) and the files that belong to one machine, such as the log, in ``%LOCALAPPDATA%``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "multazem"
WINDOWS_ICON_NAME = "multazem.ico"
# Directory name used before the application was renamed (see ``legacy_config``).
LEGACY_APP_DIR_NAME = "salah-reminder"


def is_windows() -> bool:
    """Returns whether the application runs on Windows."""
    return sys.platform == "win32"


def absolute_directory_from_environment(variable: str) -> Path | None:
    """Returns the directory named by an environment variable, or ``None`` if it is unset, empty or relative.

    The XDG specification says an empty or relative value must be ignored; the Windows folders are treated the same
    way so that a damaged environment cannot send the settings to whatever directory the program started in.

    Args:
        variable: Name of the environment variable, such as ``"XDG_CONFIG_HOME"``.
    """
    value = os.environ.get(variable, "")
    if value and Path(value).is_absolute():
        return Path(value)
    return None


def config_home() -> Path:
    """Returns the user configuration root.

    On Windows this is ``%APPDATA%``. Elsewhere it follows the XDG specification: ``XDG_CONFIG_HOME`` must be an
    absolute path, and an empty or relative value is ignored. An empty value used to yield the relative path
    ``multazem``, which made the settings land in whatever directory the app was started from.
    """
    if is_windows():
        return absolute_directory_from_environment("APPDATA") or Path.home() / "AppData" / "Roaming"
    return absolute_directory_from_environment("XDG_CONFIG_HOME") or Path.home() / ".config"


def config_dir() -> Path:
    """Returns the application's own configuration directory."""
    return config_home() / APP_DIR_NAME


def legacy_config_dir() -> Path:
    """Returns the configuration directory of the application's former name."""
    return config_home() / LEGACY_APP_DIR_NAME


def settings_file() -> Path:
    """Returns the path of ``settings.json``."""
    return config_dir() / "settings.json"


def custom_regions_file() -> Path:
    """Returns the path of ``regions.json``, which holds the regions the user added."""
    return config_dir() / "regions.json"


def local_data_dir() -> Path:
    """Returns the directory for files that belong to this machine rather than to the settings.

    It is the ``multazem`` folder of ``%LOCALAPPDATA%`` on Windows and ``$XDG_DATA_HOME/multazem`` elsewhere. The
    log file and the markers of the background process live here.
    """
    if is_windows():
        base = absolute_directory_from_environment("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        base = absolute_directory_from_environment("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def log_file() -> Path:
    """Returns the path of the log file that receives the output of a program that has no console."""
    return local_data_dir() / "multazem.log"


def windows_icon_file() -> Path | None:
    """Returns the multi-size ``.ico`` of the application, or ``None`` when it is not there.

    It is looked for in the project folder (a checkout or an editable installation) and next to the Python
    environment (the folder the Windows installer fills).
    """
    bases = (Path(__file__).resolve().parents[3], Path(sys.prefix).parent)
    for base in bases:
        candidate = base / "data" / "windows" / WINDOWS_ICON_NAME
        if candidate.is_file():
            return candidate
    return None
