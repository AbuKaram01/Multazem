# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Header-bar button that installs or removes the background service."""

from __future__ import annotations

import threading
from collections.abc import Callable

from gi.repository import Adw, GLib, Gtk

from ..i18n import tr
from ..services.background_service import (
    service_install,
    service_is_enabled,
    service_uninstall,
)


class ServiceToggleButton(Gtk.Button):
    """Starts or stops the background service that delivers notifications even when the window is closed.

    That is the ``systemd --user`` unit on Linux and the autostart entry with its background process on Windows.

    It shows an icon *and* a text label instead of a lone, ambiguous icon: this button is
    a key part of making sure notifications arrive while the app is closed, so its meaning
    must not be unclear.

    Args:
        on_message: Called with the user-facing result message after each toggle.
    """

    def __init__(self, on_message: Callable[[str], None]) -> None:
        super().__init__()
        self._on_message = on_message
        self._content = Adw.ButtonContent()
        self.set_child(self._content)
        self.connect("clicked", self._on_clicked)
        self.refresh_state()

    def refresh_state(self) -> None:
        """Updates the icon, label, tooltip and style to match whether the service is enabled."""
        if service_is_enabled():
            self._content.set_icon_name("media-playback-stop-symbolic")
            self._content.set_label(tr("window.service.stop.label"))
            self.set_tooltip_text(tr("window.service.stop.tooltip"))
            self.add_css_class("destructive-action")
            self.remove_css_class("suggested-action")
        else:
            self._content.set_icon_name("media-playback-start-symbolic")
            self._content.set_label(tr("window.service.start.label"))
            self.set_tooltip_text(tr("window.service.start.tooltip"))
            self.add_css_class("suggested-action")
            self.remove_css_class("destructive-action")

    def _on_clicked(self, _button: Gtk.Button) -> None:
        """Installs or removes the service on a worker thread, because ``systemctl`` can be slow."""
        self.set_sensitive(False)

        # systemctl can take a while, so the toggle runs on a worker thread and reports back on the main loop.
        def work() -> None:
            if service_is_enabled():
                _, message = service_uninstall()
            else:
                _, message = service_install()
            GLib.idle_add(self._finish, message)

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, message: str) -> bool:
        """Runs on the main loop after the toggle: re-enables the button and reports the result."""
        self.set_sensitive(True)
        self.refresh_state()
        self._on_message(message)
        return False
