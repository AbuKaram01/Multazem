# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The list of the day's prayer times with a notification bell per prayer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from gi.repository import Adw, Gtk

from ..core.prayer_times import PrayerTimes
from ..core.prayers import Prayer
from ..i18n import tr
from ..services.notifications import PRAYER_ICONS
from ..services.settings import Settings

BELL_ON_ICON = "multazem-bell-symbolic"
BELL_OFF_ICON = "multazem-bell-off-symbolic"
_FALLBACK_ROW_ICON = "appointment-new-symbolic"

BellChangedCallback = Callable[[Prayer, bool], None]


class PrayerTimesList(Adw.PreferencesGroup):
    """One row per timetable entry, each with its own notification bell.

    The Dhuhr row is titled "Jumu'ah" on Fridays; its bell is the same switch either way.

    Args:
        settings: Source and target of the per-prayer notification switches.
        on_bell_changed: Called as ``on_bell_changed(prayer, enabled)`` after the user toggles a bell.

    Attributes:
        rows: The row of each timetable entry.
        time_labels: The label showing each entry's time.
        bells: The bell toggle of each entry.
    """

    def __init__(self, settings: Settings, on_bell_changed: BellChangedCallback) -> None:
        super().__init__(title=tr("window.times.title"))
        self._settings = settings
        self._on_bell_changed = on_bell_changed
        # True while sync_bells() flips the toggles from the settings, so that the "toggled" handler does not
        # write the value back or announce a change the user did not make.
        self._syncing_bells = False
        self._day: date | None = None
        self.rows: dict[Prayer, Adw.ActionRow] = {}
        self.time_labels: dict[Prayer, Gtk.Label] = {}
        self.bells: dict[Prayer, Gtk.ToggleButton] = {}

        for prayer in Prayer:
            self.add(self._build_row(prayer))

    def _build_row(self, prayer: Prayer) -> Adw.ActionRow:
        """Builds the row of one timetable entry: icon, bell and time label."""
        row = Adw.ActionRow(title=self.display_name(prayer))
        row.set_icon_name(PRAYER_ICONS.get(prayer, _FALLBACK_ROW_ICON))
        self.rows[prayer] = row

        bell = Gtk.ToggleButton()
        bell.add_css_class("flat")
        bell.add_css_class("circular")
        bell.set_valign(Gtk.Align.CENTER)
        bell.set_active(self._settings.prayer_enabled(prayer))
        bell.connect("toggled", self._on_bell_toggled, prayer)
        row.add_suffix(bell)
        self.bells[prayer] = bell
        self._style_bell(prayer)

        label = Gtk.Label(label="--:--")
        label.add_css_class("numeric")
        label.add_css_class("title-4")
        label.set_valign(Gtk.Align.CENTER)
        row.add_suffix(label)
        self.time_labels[prayer] = label
        return row

    def display_name(self, prayer: Prayer) -> str:
        """Returns the name of an entry for the day on screen ("Jumu'ah" instead of "Dhuhr" on Fridays)."""
        if self._day is None:
            return tr(prayer.label_key)
        return tr(prayer.label_key_on(self._day))

    def _set_day(self, day: date) -> None:
        """Retitles the rows (and the bells' accessible text) when the date changes."""
        if day == self._day:
            return
        self._day = day
        for prayer, row in self.rows.items():
            row.set_title(self.display_name(prayer))
            self._style_bell(prayer)

    def _style_bell(self, prayer: Prayer) -> None:
        """Sets icon, sensitivity and accessible text of a bell from the current state.

        The bells are disabled while both prayer notifications and reminders are off in the settings.
        """
        bell = self.bells[prayer]
        name = self.display_name(prayer)
        globally_off = not (self._settings.notify_on_prayer or self._settings.reminder_enabled)
        if globally_off:
            text = tr("window.bell.globally_off")
        elif bell.get_active():
            text = tr("window.bell.on", prayer=name)
        else:
            text = tr("window.bell.off", prayer=name)
        bell.set_icon_name(BELL_ON_ICON if bell.get_active() else BELL_OFF_ICON)
        bell.set_sensitive(not globally_off)
        bell.set_tooltip_text(text)
        bell.update_property([Gtk.AccessibleProperty.LABEL], [text])

    def _on_bell_toggled(self, bell: Gtk.ToggleButton, prayer: Prayer) -> None:
        """Saves the user's choice and reports it; ignored while the bells are being synchronised."""
        if self._syncing_bells:
            return
        self._settings.set_prayer_enabled(prayer, bell.get_active())
        self._style_bell(prayer)
        self._on_bell_changed(prayer, bell.get_active())

    def sync_bells(self) -> None:
        """Makes every bell match the settings.

        Needed after a change from the settings dialog or from another process. The change is not
        reported through ``on_bell_changed``.
        """
        self._syncing_bells = True
        try:
            for prayer, bell in self.bells.items():
                bell.set_active(self._settings.prayer_enabled(prayer))
                self._style_bell(prayer)
        finally:
            self._syncing_bells = False

    def set_times(self, times: PrayerTimes) -> None:
        """Shows the times of a timetable and retitles the rows when its day differs from the shown one."""
        self._set_day(times.date)
        for prayer, moment in times.as_dict().items():
            label = self.time_labels.get(prayer)
            if label is not None:
                label.set_text(moment.strftime("%H:%M"))

    def highlight(self, upcoming: Prayer | None) -> None:
        """Colours the time of the upcoming prayer and clears the others.

        Args:
            upcoming: The prayer to highlight, or ``None`` to clear every highlight.
        """
        for prayer, label in self.time_labels.items():
            if prayer is upcoming:
                label.add_css_class("accent")
            else:
                label.remove_css_class("accent")
