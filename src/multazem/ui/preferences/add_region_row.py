# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Expandable form that adds a user-defined region to the offline regions list."""

from __future__ import annotations

import itertools
from collections.abc import Callable

from gi.repository import Adw, Gtk

from ...core.regions import Region, RegionValidationError
from ...i18n import LocalizedError, describe_error, tr
from ...services.region_catalog import RegionCatalog

RegionAddedCallback = Callable[[Region], None]
ErrorCallback = Callable[[str], None]


class AddRegionRow(Adw.ExpanderRow):
    """Name, latitude, longitude and time zone fields plus an "Add" button.

    The time zone is optional: it is pre-filled with the one currently configured and an
    empty value falls back to it, so a user who only knows a place's name and coordinates
    can still add it.

    Args:
        catalog: The catalog the new region is added to.
        current_timezone: Returns the time zone currently configured, used to pre-fill the form.
        on_added: Called with the new region after it was saved.
        on_error: Called with a localized message when the input is invalid or saving failed.
    """

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
        """Makes Enter move to the next field and, in the last one, add the region."""
        rows = list(self._fields.values())
        for row, following in itertools.pairwise(rows):
            row.connect("entry-activated", lambda *_, target=following: target.grab_focus())
        rows[-1].connect("entry-activated", lambda *_: self._submit())

    def _build_button_row(self) -> Adw.ActionRow:
        """Builds the row with the "Add" button."""
        row = Adw.ActionRow()
        button = Gtk.Button(label=tr("prefs.region.add.button"))
        button.set_valign(Gtk.Align.CENTER)
        button.add_css_class("suggested-action")
        button.connect("clicked", lambda _button: self._submit())
        row.add_suffix(button)
        row.set_activatable_widget(button)
        return row

    def _reset_timezone(self) -> None:
        """Pre-fills the time-zone field with the currently configured zone."""
        self._prefilled_timezone = self._current_timezone()
        self._timezone_row.set_text(self._prefilled_timezone)

    def _on_expanded_changed(self, _row: Adw.ExpanderRow, _pspec: object) -> None:
        """Refreshes the pre-filled time zone when the form opens, unless the user already edited it."""
        if self.get_expanded() and self._timezone_row.get_text() == self._prefilled_timezone:
            self._reset_timezone()

    def _submit(self) -> None:
        """Validates the form and adds the region; on failure marks the offending field and reports it."""
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
        """Empties the typed fields and restores the pre-filled time zone."""
        for field in ("name", "latitude", "longitude"):
            self._fields[field].set_text("")
        self._reset_timezone()
