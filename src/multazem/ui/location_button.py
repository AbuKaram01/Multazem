# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Header-bar button that detects the location through the IP address."""

from __future__ import annotations

from collections.abc import Callable

from gi.repository import Gtk

from ..i18n import tr
from ..services.location import LocationManager

_IDLE_ICON = "find-location-symbolic"
_BUSY_ICON = "content-loading-symbolic"

DetectedCallback = Callable[[float, float, str, str], None]
ErrorCallback = Callable[[str], None]


class DetectLocationButton(Gtk.Button):
    """Button that starts an IP-based location lookup and shows a busy icon while it runs.

    Args:
        on_detected: Called as ``on_detected(latitude, longitude, timezone_name, city)`` on success.
        on_error: Called with a localized message when the lookup fails.
    """

    def __init__(self, on_detected: DetectedCallback, on_error: ErrorCallback) -> None:
        super().__init__(icon_name=_IDLE_ICON)
        self._on_detected = on_detected
        self._on_error = on_error
        self.set_tooltip_text(tr("window.detect_location.tooltip"))
        self.connect("clicked", self._on_clicked)

    def _on_clicked(self, _button: Gtk.Button) -> None:
        """Disables the button, shows the busy icon and starts the lookup."""
        self.set_sensitive(False)
        self.set_icon_name(_BUSY_ICON)
        LocationManager(self._handle_location, self._handle_error).request()

    def _restore(self) -> None:
        """Re-enables the button and shows the idle icon."""
        self.set_sensitive(True)
        self.set_icon_name(_IDLE_ICON)

    def _handle_location(self, latitude: float, longitude: float, tz_name: str, city: str) -> None:
        """Passes a detected location on and restores the button, even if the callback raises."""
        try:
            self._on_detected(latitude, longitude, tz_name, city)
        finally:
            self._restore()

    def _handle_error(self, message: str) -> None:
        """Restores the button and reports the error message."""
        self._restore()
        self._on_error(message)
