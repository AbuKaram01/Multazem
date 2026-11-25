# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Card showing the next prayer, its time and a live countdown."""

from __future__ import annotations

from gi.repository import Gtk

from ..i18n import tr

_CARD_PADDING = 20
_LINE_SPACING = 6


def _label(*css_classes: str, text: str = "") -> Gtk.Label:
    """Creates a label with the given CSS classes and text."""
    label = Gtk.Label(label=text)
    for css_class in css_classes:
        label.add_css_class(css_class)
    return label


class NextPrayerCard(Gtk.Box):
    """Card with the name of the next prayer, its time and the countdown to it."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.add_css_class("card")

        self._name_label = _label("title-1")
        self._time_label = _label("title-3", "accent")
        self._countdown_label = _label("caption", "dim-label")

        inner = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=_LINE_SPACING,
            halign=Gtk.Align.CENTER,
            margin_top=_CARD_PADDING,
            margin_bottom=_CARD_PADDING,
            margin_start=_CARD_PADDING,
            margin_end=_CARD_PADDING,
        )
        inner.append(_label("caption", "dim-label", text=tr("window.next_prayer")))
        for widget in (self._name_label, self._time_label, self._countdown_label):
            inner.append(widget)
        self.append(inner)

    def show_prayer(self, name: str, time_text: str, countdown_text: str) -> None:
        """Replaces the three lines of the card.

        Args:
            name: Display name of the prayer.
            time_text: Its start time as ``HH:MM``.
            countdown_text: The formatted time remaining.
        """
        self._name_label.set_text(name)
        self._time_label.set_text(time_text)
        self._countdown_label.set_text(countdown_text)

    @property
    def name_text(self) -> str:
        """The text of the prayer-name line (used by the tests)."""
        return self._name_label.get_text()

    @property
    def countdown_text(self) -> str:
        """The text of the countdown line (used by the tests)."""
        return self._countdown_label.get_text()
