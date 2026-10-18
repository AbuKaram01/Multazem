# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from gi.repository import Adw, Gtk

from ...i18n import LANGUAGE_NAMES, SUPPORTED_LANGUAGES, tr
from ...services.settings import Settings
from ..bindings import bind_switch_row


class AppearanceGroup(Adw.PreferencesGroup):
    def __init__(self, settings: Settings) -> None:
        super().__init__(title=tr("prefs.appearance.title"))
        self._settings = settings
        self.add(self._build_language_row())

        hijri_row = Adw.SwitchRow(title=tr("prefs.hijri.show"))
        bind_switch_row(hijri_row, settings, "show_hijri")
        self.add(hijri_row)

        sync_row = Adw.SwitchRow(title=tr("prefs.hijri.sync.title"), subtitle=tr("prefs.hijri.sync.subtitle"))
        bind_switch_row(sync_row, settings, "sync_hijri_online")
        self.add(sync_row)

    def _build_language_row(self) -> Adw.ComboRow:
        row = Adw.ComboRow(title=tr("prefs.language.title"), subtitle=tr("prefs.language.subtitle"))
        row.set_model(Gtk.StringList.new([LANGUAGE_NAMES[code] for code in SUPPORTED_LANGUAGES]))
        row.set_selected(SUPPORTED_LANGUAGES.index(self._settings.language))
        row.connect("notify::selected", self._on_language_selected)
        return row

    def _on_language_selected(self, row: Adw.ComboRow, _pspec: object) -> None:
        self._settings.language = SUPPORTED_LANGUAGES[row.get_selected()]
