# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


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
    def __init__(self, on_detected: DetectedCallback, on_error: ErrorCallback) -> None:
        super().__init__(icon_name=_IDLE_ICON)
        self._on_detected = on_detected
        self._on_error = on_error
        self.set_tooltip_text(tr("window.detect_location.tooltip"))
        self.connect("clicked", self._on_clicked)

    def _on_clicked(self, _button: Gtk.Button) -> None:
        self.set_sensitive(False)
        self.set_icon_name(_BUSY_ICON)
        LocationManager(self._handle_location, self._handle_error).request()

    def _restore(self) -> None:
        self.set_sensitive(True)
        self.set_icon_name(_IDLE_ICON)

    def _handle_location(self, latitude: float, longitude: float, tz_name: str, city: str) -> None:
        try:
            self._on_detected(latitude, longitude, tz_name, city)
        finally:
            self._restore()

    def _handle_error(self, message: str) -> None:
        self._restore()
        self._on_error(message)
