# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Header card of the main window: date, Hijri date and the selected place."""

from __future__ import annotations

from datetime import date

from gi.repository import Adw, Gtk

from ..i18n import tr
from .formatting import format_weekday_and_date


class DateCard(Adw.PreferencesGroup):
    """Shows today's date, the Hijri date (optional) and the name of the selected city."""

    def __init__(self) -> None:
        super().__init__()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        box.set_halign(Gtk.Align.CENTER)

        self._date_label = Gtk.Label()
        self._date_label.add_css_class("title-2")

        self._hijri_label = Gtk.Label()
        self._hijri_label.add_css_class("caption")
        self._hijri_label.add_css_class("dim-label")
        self._hijri_label.set_tooltip_text(tr("window.hijri.tooltip.estimated"))

        self._city_label = Gtk.Label()
        self._city_label.add_css_class("caption")

        box.append(self._date_label)
        box.append(self._hijri_label)
        box.append(self._city_label)
        self.add(box)

    def set_date(self, day: date) -> None:
        """Shows the weekday and date of ``day`` in the active language."""
        self._date_label.set_text(format_weekday_and_date(day))

    def set_hijri(self, text: str | None, official: bool = False) -> None:
        """Shows the Hijri date, or hides the line when ``text`` is ``None``.

        Args:
            text: The formatted Hijri date, or ``None`` to hide the line.
            official: Selects the tooltip: synced with Dar al-Ifta (``True``) or a local estimate.
        """
        if text is None:
            self._hijri_label.set_visible(False)
            return
        self._hijri_label.set_text(text)
        tooltip_key = "official" if official else "estimated"
        self._hijri_label.set_tooltip_text(tr(f"window.hijri.tooltip.{tooltip_key}"))
        self._hijri_label.set_visible(True)

    def set_city(self, city: str) -> None:
        """Shows the name of the selected city."""
        self._city_label.set_text(f"📍 {city}")

    @property
    def date_text(self) -> str:
        """The text of the date line (used by the tests)."""
        return self._date_label.get_text()

    @property
    def city_text(self) -> str:
        """The text of the city line (used by the tests)."""
        return self._city_label.get_text()
