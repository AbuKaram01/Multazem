# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Desktop notifications: ``notify-send`` on Linux, a toast on Windows.

``notify-send`` talks to the freedesktop Notifications service over D-Bus, a standard that
works on every Linux desktop environment, not just GNOME. On Windows the toast is raised by
:mod:`multazem.services.windows_toast`.
"""

from __future__ import annotations

import shutil
import subprocess

from ..core.prayers import Prayer
from ..i18n import tr
from ..logs import get_logger
from .paths import is_windows
from .windows_toast import send_toast

logger = get_logger("notification")

NOTIFY_TIMEOUT_SECONDS = 5
DEFAULT_ICON = "appointment-soon-symbolic"

# One icon per timetable entry. Sunrise uses a sunrise icon and Maghrib a sunset icon: "emblem-default-symbolic"
# rendered as a distorted sticker in the modern Adwaita theme, and these exist in every theme version.
PRAYER_ICONS: dict[Prayer, str] = {
    Prayer.FAJR: "weather-clear-night-symbolic",
    Prayer.SUNRISE: "daytime-sunrise-symbolic",
    Prayer.DHUHR: "weather-clear-symbolic",
    Prayer.ASR: "weather-few-clouds-symbolic",
    Prayer.MAGHRIB: "daytime-sunset-symbolic",
    Prayer.ISHA: "weather-clear-night-symbolic",
}


def send_notification(title: str, body: str, icon: str = DEFAULT_ICON) -> tuple[bool, str]:
    """Sends a notification and reports what happened as ``(succeeded, error_detail)``.

    The call used to be fire-and-forget (``Popen`` without waiting). When ``notify-send``
    failed (no D-Bus session bus, or no notification daemon running) nobody could tell,
    and it merely looked like "notifications never arrive" with no explanation. Waiting
    for the real result lets the caller show the actual reason to the user.

    ``error_detail`` is a technical diagnostic and intentionally stays in English. A failure is also
    logged as a warning.

    Args:
        title: Notification title.
        body: Notification text.
        icon: Name of a themed icon. Windows toasts carry the application's own icon instead.

    Returns:
        ``(True, "")`` on success, otherwise ``(False, reason)``.
    """
    if is_windows():
        succeeded, detail = send_toast(title, body)
        return (True, "") if succeeded else _failure(detail)

    if shutil.which("notify-send") is None:
        return _failure("notify-send is not installed (libnotify-bin package)")

    try:
        result = subprocess.run(
            _notify_send_command(title, body, icon),
            capture_output=True,
            text=True,
            timeout=NOTIFY_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _failure(
            f"notify-send did not answer within {NOTIFY_TIMEOUT_SECONDS} seconds (is the D-Bus session bus running?)"
        )
    except (OSError, subprocess.SubprocessError) as error:
        return _failure(str(error))

    if result.returncode != 0:
        detail = result.stderr.strip() or f"notify-send exited with code {result.returncode}"
        return _failure(detail)
    return True, ""


def _notify_send_command(title: str, body: str, icon: str) -> list[str]:
    """Returns the ``notify-send`` command line for one notification."""
    return ["notify-send", "--icon", icon, "--urgency", "normal", "--app-name", tr("app.name"), title, body]


def _failure(detail: str) -> tuple[bool, str]:
    """Logs ``detail`` as a warning and returns the ``(False, detail)`` result of a failed send."""
    logger.warning("%s", detail)
    return False, detail
