# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from gi.repository import Adw, Gtk

from ...i18n import tr
from ...services.region_catalog import RegionCatalog
from ...services.settings import Settings
from ..toasts import make_toast
from .appearance_group import AppearanceGroup
from .calculation_group import CalculationGroup
from .location_group import LocationGroup
from .notification_group import NotificationGroup

DEFAULT_WIDTH = 460
DEFAULT_HEIGHT = 600
TOAST_TIMEOUT_SECONDS = 4


class PreferencesDialog(Adw.Window):
    def __init__(self, settings: Settings, catalog: RegionCatalog, parent: Gtk.Window) -> None:
        super().__init__()
        self._settings = settings
        self._catalog = catalog
        self.set_default_size(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_resizable(False)

        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)
        self.rebuild()

    def rebuild(self) -> None:
        self.set_title(tr("prefs.title"))

        page = Adw.PreferencesPage()
        page.add(LocationGroup(self._settings, self._catalog, self._show_toast))
        page.add(CalculationGroup(self._settings, self))
        page.add(NotificationGroup(self._settings, self._show_toast))
        page.add(AppearanceGroup(self._settings))

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(page)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(Adw.HeaderBar())
        root.append(scroll)
        self._toast_overlay.set_child(root)

    def _show_toast(self, message: str) -> None:
        self._toast_overlay.add_toast(make_toast(message, TOAST_TIMEOUT_SECONDS))
