# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Location settings: offline region picker, manual coordinates and region adding."""

from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ...core.coordinates import MAX_LATITUDE, MAX_LONGITUDE
from ...core.regions import Region
from ...core.timeutil import is_valid_timezone
from ...i18n import current_language, tr
from ...services.region_catalog import RegionCatalog
from ...services.settings import Settings
from .add_region_row import AddRegionRow

_COORDINATE_STEP = 0.01
_COORDINATE_PAGE_STEP = 1.0
_COORDINATE_DIGITS = 4


class LocationGroup(Adw.PreferencesGroup):
    """Preferences group for the location: region picker, city name, coordinates and time zone.

    Choosing a region fills the other fields; editing a field changes only that setting.

    Args:
        settings: The settings to read and write.
        catalog: The offline region catalog.
        show_toast: Shows a message to the user.
    """

    def __init__(
        self,
        settings: Settings,
        catalog: RegionCatalog,
        show_toast: Callable[[str], None],
    ) -> None:
        super().__init__(title=tr("prefs.location.title"), description=tr("prefs.location.description"))
        self._settings = settings
        self._catalog = catalog
        self._show_toast = show_toast
        self._regions: list[Region] = []
        # True while the picker is refilled by code, so that this does not count as the user picking a region.
        self._updating_picker = False

        self._picker_row = self._build_picker_row()
        self._city_row = self._build_city_row()
        self._latitude_row = self._build_coordinate_row(
            "prefs.latitude", -MAX_LATITUDE, MAX_LATITUDE, settings.latitude, "latitude"
        )
        self._longitude_row = self._build_coordinate_row(
            "prefs.longitude", -MAX_LONGITUDE, MAX_LONGITUDE, settings.longitude, "longitude"
        )
        self._timezone_row = self._build_timezone_row()
        self._add_region_row = AddRegionRow(
            catalog,
            current_timezone=lambda: settings.timezone_name,
            on_added=self._on_region_added,
            on_error=show_toast,
        )

        for row in (
            self._picker_row,
            self._city_row,
            self._latitude_row,
            self._longitude_row,
            self._timezone_row,
            self._add_region_row,
        ):
            self.add(row)

        self._reload_picker()

    def _build_picker_row(self) -> Adw.ComboRow:
        """Builds the searchable list of offline regions: built-in cities plus the user's own."""
        row = Adw.ComboRow(title=tr("prefs.picker.title"))
        row.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        row.set_enable_search(True)
        row.connect("notify::selected", self._on_region_picked)
        return row

    def _build_city_row(self) -> Adw.EntryRow:
        """Builds the editable city name."""
        row = Adw.EntryRow(title=tr("prefs.city_name"))
        row.set_text(self._catalog.display_name(self._settings.city_name, current_language()))
        row.connect("changed", lambda r: setattr(self._settings, "city_name", r.get_text()))
        return row

    def _build_coordinate_row(
        self, title_key: str, minimum: float, maximum: float, value: float, attribute: str
    ) -> Adw.SpinRow:
        """Builds a latitude or longitude spin row that writes to ``settings.<attribute>``."""
        row = Adw.SpinRow.new_with_range(minimum, maximum, _COORDINATE_STEP)
        row.set_title(tr(title_key))
        row.set_digits(_COORDINATE_DIGITS)
        row.set_value(value)
        row.get_adjustment().set_page_increment(_COORDINATE_PAGE_STEP)
        row.connect("changed", lambda r: setattr(self._settings, attribute, r.get_value()))
        return row

    def _build_timezone_row(self) -> Adw.EntryRow:
        """Builds the time-zone field."""
        row = Adw.EntryRow(title=tr("prefs.timezone.title"))
        row.set_text(self._settings.timezone_name)
        row.set_tooltip_text(tr("prefs.timezone.tooltip"))
        row.connect("changed", self._on_timezone_changed)
        return row

    def _on_timezone_changed(self, row: Adw.EntryRow) -> None:
        """Stores a valid time zone; an invalid one is flagged and not stored."""
        text = row.get_text().strip()
        if not is_valid_timezone(text):
            row.add_css_class("error")
            row.set_title(tr("prefs.timezone.invalid"))
            return
        row.remove_css_class("error")
        row.set_title(tr("prefs.timezone.title"))
        self._settings.timezone_name = text

    def _on_region_picked(self, row: Adw.ComboRow, _pspec: object) -> None:
        """Applies the region the user picked; ignored while the picker is refilled by code."""
        if self._updating_picker:
            return
        index = row.get_selected()
        if index == Gtk.INVALID_LIST_POSITION or index >= len(self._regions):
            return
        self._apply_region(self._regions[index])

    def _on_region_added(self, region: Region) -> None:
        """Selects the new region, which also makes it the current location."""
        self._reload_picker(select=region)
        self._show_toast(tr("prefs.region.added", name=region.name(current_language())))

    def _reload_picker(self, select: Region | None = None) -> None:
        """Refills the picker.

        Selects ``select`` (applying it) when given, otherwise reflects the saved city.
        """
        language = current_language()
        self._regions = self._catalog.regions(language)
        self._updating_picker = True
        try:
            self._picker_row.set_model(Gtk.StringList.new([region.name(language) for region in self._regions]))
            self._picker_row.set_subtitle(tr("prefs.picker.subtitle", count=len(self._regions)))
            current = self._catalog.find_by_name(self._settings.city_name)
            self._picker_row.set_selected(self._index_of(current))
        finally:
            self._updating_picker = False
        if select is not None:
            self._picker_row.set_selected(self._index_of(select))

    def _index_of(self, region: Region | None) -> int:
        """Returns the picker position of ``region``, or ``Gtk.INVALID_LIST_POSITION`` when it is not listed."""
        try:
            return self._regions.index(region) if region is not None else Gtk.INVALID_LIST_POSITION
        except ValueError:
            return Gtk.INVALID_LIST_POSITION

    def _apply_region(self, region: Region) -> None:
        """Makes ``region`` the current location, in the form and in the settings."""
        name = region.name(current_language())
        self._city_row.set_text(name)
        self._latitude_row.set_value(region.latitude)
        self._longitude_row.set_value(region.longitude)
        self._timezone_row.set_text(region.timezone)
        self._settings.city_name = name
        self._settings.latitude = region.latitude
        self._settings.longitude = region.longitude
        self._settings.timezone_name = region.timezone
