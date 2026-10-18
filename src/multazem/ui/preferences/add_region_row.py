# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ...core.regions import Region, RegionValidationError
from ...i18n import LocalizedError, describe_error, tr
from ...services.region_catalog import RegionCatalog

RegionAddedCallback = Callable[[Region], None]
ErrorCallback = Callable[[str], None]


class AddRegionRow(Adw.ExpanderRow):
    def __init__(
        self,
        catalog: RegionCatalog,
        current_timezone: Callable[[], str],
        on_added: RegionAddedCallback,
        on_error: ErrorCallback,
    ) -> None:
        super().__init__(title=tr("prefs.region.add.title"), subtitle=tr("prefs.region.add.subtitle"))
        self.set_icon_name("list-add-symbolic")
        self._catalog = catalog
        self._current_timezone = current_timezone
        self._on_added = on_added
        self._on_error = on_error

        self._name_row = Adw.EntryRow(title=tr("prefs.region.name"))
        self._latitude_row = Adw.EntryRow(title=tr("prefs.region.latitude"))
        self._longitude_row = Adw.EntryRow(title=tr("prefs.region.longitude"))
        self._timezone_row = Adw.EntryRow(title=tr("prefs.region.timezone"))
        self._timezone_row.set_tooltip_text(tr("prefs.region.timezone.tooltip"))
        self._prefilled_timezone = ""

        self._fields = {
            "name": self._name_row,
            "latitude": self._latitude_row,
            "longitude": self._longitude_row,
            "timezone": self._timezone_row,
        }
        for row in self._fields.values():
            self.add_row(row)
            row.connect("changed", lambda changed_row: changed_row.remove_css_class("error"))
        self.add_row(self._build_button_row())
        self._chain_enter_key()

        self._reset_timezone()
        self.connect("notify::expanded", self._on_expanded_changed)

    def _chain_enter_key(self) -> None:
        """Enter moves to the next field and, in the last one, adds the region."""
        rows = list(self._fields.values())
        for row, following in zip(rows, rows[1:], strict=False):
            row.connect("entry-activated", lambda *_, target=following: target.grab_focus())
        rows[-1].connect("entry-activated", lambda *_: self._submit())

    def _build_button_row(self) -> Adw.ActionRow:
        row = Adw.ActionRow()
        button = Gtk.Button(label=tr("prefs.region.add.button"))
        button.set_valign(Gtk.Align.CENTER)
        button.add_css_class("suggested-action")
        button.connect("clicked", lambda _button: self._submit())
        row.add_suffix(button)
        row.set_activatable_widget(button)
        return row

    def _reset_timezone(self) -> None:
        self._prefilled_timezone = self._current_timezone()
        self._timezone_row.set_text(self._prefilled_timezone)

    def _on_expanded_changed(self, _row: Adw.ExpanderRow, _pspec: object) -> None:
        if self.get_expanded() and self._timezone_row.get_text() == self._prefilled_timezone:
            self._reset_timezone()

    def _submit(self) -> None:
        for row in self._fields.values():
            row.remove_css_class("error")
        timezone = self._timezone_row.get_text().strip() or self._current_timezone()
        try:
            region = self._catalog.add(
                self._name_row.get_text(),
                self._latitude_row.get_text(),
                self._longitude_row.get_text(),
                timezone,
            )
        except RegionValidationError as error:
            self._fields[error.field].add_css_class("error")
            self._fields[error.field].grab_focus()
            self._on_error(describe_error(error))
            return
        except LocalizedError as error:
            self._on_error(describe_error(error))
            return

        self._clear_form()
        self.set_expanded(False)
        self._on_added(region)

    def _clear_form(self) -> None:
        for field in ("name", "latitude", "longitude"):
            self._fields[field].set_text("")
        self._reset_timezone()
