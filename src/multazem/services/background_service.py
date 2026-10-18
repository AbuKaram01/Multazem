# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The background service of the current platform, behind one interface.

The notifications must keep arriving after the window is closed. On Linux a ``systemd --user`` unit takes care
of that (:mod:`multazem.services.systemd_service`); on Windows it is autostart plus a background process
(:mod:`multazem.services.windows_service`). The interface calls these functions and never asks which system
it runs on.
"""

from __future__ import annotations

import contextlib
from contextlib import AbstractContextManager
from types import ModuleType

from . import systemd_service, windows_service
from .paths import is_windows


def _implementation() -> ModuleType:
    """Returns the module that manages the background service of this platform."""
    return windows_service if is_windows() else systemd_service


def service_is_enabled() -> bool:
    """Returns whether the background service starts with the session."""
    return _implementation().service_is_enabled()


def service_is_active() -> bool:
    """Returns whether the background service is running right now."""
    return _implementation().service_is_active()


def service_install() -> tuple[bool, str]:
    """Enables the background service and starts it; returns ``(succeeded, message for the user)``."""
    return _implementation().service_install()


def service_uninstall() -> tuple[bool, str]:
    """Disables the background service and stops it; returns ``(succeeded, message for the user)``."""
    return _implementation().service_uninstall()


def prepare_service() -> bool:
    """Does the start-up housekeeping of the background service.

    Linux replaces the unit of the application's former name. Windows points autostart at the installation
    that is running. Both run external commands or touch the registry, so call this off the interface thread.

    Returns:
        ``True`` when something was changed.
    """
    if is_windows():
        return windows_service.refresh_autostart()
    return systemd_service.migrate_legacy_service()


def register_background_process() -> AbstractContextManager[bool]:
    """Marks the calling process as the background process while the returned context is open.

    Only Windows needs this (systemd knows which process it started). Elsewhere the context does nothing and
    reports success.

    Returns:
        A context manager that yields ``True`` when the process may run as the background process and ``False``
        when another one already does.
    """
    if is_windows():
        return windows_service.background_process_presence()
    return contextlib.nullcontext(True)
