# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Main window: next-prayer card, the day's prayer times and the header-bar actions."""

from __future__ import annotations

from datetime import date, datetime

from gi.repository import Adw, Gio, GLib, Gtk

from ..core.hijri import HijriDate, to_hijri
from ..core.prayers import Prayer
from ..core.schedule import PrayerSchedule
from ..core.timeutil import local_now
from ..i18n import current_language, describe_error, tr
from ..logs import get_logger
from ..services.background_service import service_is_active
from ..services.hijri_sync import HijriSync
from ..services.region_catalog import RegionCatalog
from ..services.scheduler import NotificationScheduler
from ..services.settings import Settings
from .date_card import DateCard
from .formatting import format_countdown
from .language import apply_ui_language
from .location_button import DetectLocationButton
from .next_prayer_card import NextPrayerCard
from .prayer_list import PrayerTimesList
from .preferences import PreferencesDialog
from .service_button import ServiceToggleButton
from .toasts import make_toast

logger = get_logger("window")

DEFAULT_WIDTH = 480
DEFAULT_HEIGHT = 680
SETTINGS_REFRESH_DELAY_MS = 250
BACKGROUND_HIDE_DELAY_MS = 2500
CLOCK_TICK_MS = 1000
CONTENT_MAX_WIDTH = 440
CONTENT_SPACING = 16
CONTENT_MARGIN_TOP = 20
CONTENT_MARGIN_BOTTOM = 24
CONTENT_MARGIN_SIDES = 16


class MultazemWindow(Adw.ApplicationWindow):
    """The main window.

    Shows the date cards, the next prayer with a live countdown and the day's timetable. It keeps
    them current with a one-second timer, follows settings changes (made here or by another process)
    and rebuilds itself when the language changes.

    Closing the window does not stop notifications: if the background service is running the whole
    application quits, otherwise the window is hidden and the application keeps running.

    Args:
        app: The application that owns the window.
        settings: The settings to display and listen to.
        scheduler: The notification scheduler, refreshed whenever the timetable inputs change.
        catalog: The region catalog, used to show the city name in the active language.
    """

    def __init__(
        self,
        app: Adw.Application,
        settings: Settings,
        scheduler: NotificationScheduler,
        catalog: RegionCatalog,
    ) -> None:
        super().__init__(application=app)
        self._settings = settings
        self._scheduler = scheduler
        self._catalog = catalog
        self._schedule: PrayerSchedule | None = None
        self._last_day_checked: date | None = None
        self._settings_refresh_source: int | None = None
        self._pref_dialog: PreferencesDialog | None = None
        self._close_notice_shown = False
        self._hijri_sync = HijriSync()

        self.set_default_size(DEFAULT_WIDTH, DEFAULT_HEIGHT)
        self.set_resizable(True)

        preferences_action = Gio.SimpleAction.new("preferences", None)
        preferences_action.connect("activate", self._open_preferences)
        self.add_action(preferences_action)

        self._build_ui()
        self._refresh_times()
        self._last_day_checked = self._today()
        self._settings.add_listener(self._on_setting_changed)
        # The timer runs for the life of the window; _tick() always returns True to keep it going.
        GLib.timeout_add(CLOCK_TICK_MS, self._tick)

    def _build_ui(self) -> None:
        """(Re)builds every widget. Called again when the language changes."""
        self.set_title(tr("app.name"))
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.append(self._build_header())
        root.append(self._build_content())

        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(root)
        self.set_content(self._toast_overlay)

    def _build_header(self) -> Adw.HeaderBar:
        """Builds the header bar: the menu, the location-detection button and the service button."""
        header = Adw.HeaderBar()
        header.set_centering_policy(Adw.CenteringPolicy.LOOSE)

        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic")
        menu_button.set_tooltip_text(tr("window.menu.tooltip"))
        menu_button.set_menu_model(self._build_menu())
        header.pack_end(menu_button)

        self._location_button = DetectLocationButton(on_detected=self._on_location_detected, on_error=self._show_toast)
        header.pack_start(self._location_button)
        self._service_button = ServiceToggleButton(on_message=self._show_toast)
        header.pack_start(self._service_button)
        return header

    def _build_content(self) -> Gtk.ScrolledWindow:
        """Builds the scrolling content: the date card, the next-prayer card and the timetable."""
        self._date_card = DateCard()
        self._next_card = NextPrayerCard()
        self._prayer_list = PrayerTimesList(self._settings, self._on_bell_changed)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=CONTENT_SPACING,
            margin_top=CONTENT_MARGIN_TOP,
            margin_bottom=CONTENT_MARGIN_BOTTOM,
            margin_start=CONTENT_MARGIN_SIDES,
            margin_end=CONTENT_MARGIN_SIDES,
        )
        for card in (self._date_card, self._next_card, self._prayer_list):
            content.append(card)

        clamp = Adw.Clamp(maximum_size=CONTENT_MAX_WIDTH)
        clamp.set_child(content)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        scroll.set_child(clamp)
        return scroll

    @staticmethod
    def _build_menu() -> Gio.Menu:
        """Builds the main menu: preferences, about and quit."""
        menu = Gio.Menu()
        preferences_section = Gio.Menu()
        preferences_section.append(tr("menu.preferences"), "win.preferences")
        menu.append_section(None, preferences_section)
        app_section = Gio.Menu()
        app_section.append(tr("menu.about"), "app.about")
        app_section.append(tr("menu.quit"), "app.quit")
        menu.append_section(None, app_section)
        return menu

    def _apply_language(self) -> None:
        """Switches every visible string and the text direction to the selected language."""
        apply_ui_language(self._settings.language)
        self._build_ui()
        self._refresh_times()
        if self._pref_dialog is not None:
            self._pref_dialog.rebuild()

    def _on_setting_changed(self, _key: str) -> None:
        """Settings listener: schedules one refresh shortly after a change, so a burst of changes costs one."""
        if self._settings_refresh_source is None:
            self._settings_refresh_source = GLib.timeout_add(SETTINGS_REFRESH_DELAY_MS, self._apply_setting_changes)

    def _apply_setting_changes(self) -> bool:
        """Applies the pending settings changes: a new language rebuilds the UI, anything else recalculates."""
        self._settings_refresh_source = None
        if current_language() != self._settings.language:
            self._apply_language()
        else:
            self._refresh_times()
        return False

    def _on_bell_changed(self, prayer: Prayer, enabled: bool) -> None:
        """Tells the scheduler about a toggled bell and confirms it with a toast."""
        self._scheduler.refresh()
        state_key = "window.toast.bell_on" if enabled else "window.toast.bell_off"
        self._show_toast(tr(state_key, prayer=self._prayer_list.display_name(prayer)))

    def _on_location_detected(self, latitude: float, longitude: float, tz_name: str, city: str) -> None:
        """Stores a detected location and recalculates the timetable."""
        self._settings.latitude = latitude
        self._settings.longitude = longitude
        self._settings.timezone_name = tz_name
        self._settings.city_name = city
        if self._refresh_times():
            self._show_toast(tr("window.toast.location_set", city=city))

    def _local_now(self) -> datetime:
        """Returns the current wall-clock time at the configured location.

        Falls back to the machine's own time when the configured time zone is invalid.
        """
        try:
            return local_now(self._settings.timezone_name)
        except ValueError:
            return datetime.now()

    def _today(self) -> date:
        """Returns "today" at the configured location (not on the machine's clock)."""
        return self._local_now().date()

    def _refresh_times(self) -> bool:
        """Recalculates the schedule from the settings.

        Returns:
            ``False`` if the calculation failed; the error is shown as a toast.
        """
        try:
            schedule = PrayerSchedule(self._settings.calculation_params)
        except ValueError as error:
            self._show_toast(f"⚠️ {describe_error(error)}")
            self._update_ui()
            return False

        self._schedule = schedule
        self._prayer_list.sync_bells()
        self._scheduler.refresh()
        self._update_ui()
        return True

    def _tick(self) -> bool:
        """One-second timer: recalculates when the day changed, then updates the highlight and countdown."""
        today = self._today()
        if today != self._last_day_checked:
            self._last_day_checked = today
            if self._schedule is None or self._schedule.today.date != today:
                self._refresh_times()
        self._update_highlights()
        self._update_countdown()
        return True

    def _update_ui(self) -> None:
        """Redraws everything that depends on the schedule and the settings."""
        now = self._local_now()
        today = now.date()
        self._date_card.set_date(today)
        self._update_hijri(today)
        self._date_card.set_city(self._catalog.display_name(self._settings.city_name, current_language()))

        if self._schedule is None:
            return
        self._prayer_list.set_times(self._schedule.today)
        self._update_highlights(now)
        self._update_countdown(now)

    def _update_hijri(self, today: date) -> None:
        """Shows the Hijri date: the official one when online sync is on and known, otherwise the estimate."""
        if not self._settings.show_hijri:
            self._date_card.set_hijri(None)
            return
        official = None
        if self._settings.sync_hijri_online:
            official = self._hijri_sync.cached(today)
            if official is None:
                self._hijri_sync.request(today, self._on_hijri_synced)
        if official is not None:
            self._date_card.set_hijri(official.format(current_language()), official=True)
        else:
            self._date_card.set_hijri(to_hijri(today).format(current_language()))

    def _on_hijri_synced(self, day: date, result: HijriDate | None) -> None:
        """Shows the official Hijri date once it arrives, unless the day or the settings changed meanwhile."""
        if day != self._today():
            return
        if result and self._settings.show_hijri and self._settings.sync_hijri_online:
            self._date_card.set_hijri(result.format(current_language()), official=True)

    def _update_highlights(self, now: datetime | None = None) -> None:
        """Colours the row of the upcoming prayer.

        Kept separate from :meth:`_update_ui` so it can run on every tick. It used to be
        refreshed only on start-up, at midnight and after the settings closed, so when the
        upcoming prayer changed (Dhuhr passed, Asr became next) while the window was open,
        the highlight stayed stuck on the old prayer until something else redrew the screen.
        """
        if self._schedule is None:
            return
        upcoming = self._schedule.today.next_prayer(now)
        self._prayer_list.highlight(upcoming[0] if upcoming else None)

    def _update_countdown(self, now: datetime | None = None) -> None:
        """Updates the next-prayer card; after Isha it counts down to tomorrow's Fajr."""
        if self._schedule is None:
            return
        upcoming = self._schedule.next_prayer(now)
        if upcoming is None:
            return
        remaining = self._schedule.seconds_until(upcoming.when)
        self._next_card.show_prayer(
            tr(upcoming.prayer.label_key_on(upcoming.when.date())),
            upcoming.when.strftime("%H:%M"),
            format_countdown(remaining),
        )

    def _show_toast(self, message: str) -> None:
        """Shows a message over the window."""
        self._toast_overlay.add_toast(make_toast(message))

    def _open_preferences(self, *_args: object) -> None:
        """Opens the preferences dialog, or brings the already open one to the front."""
        if self._pref_dialog is not None:
            self._pref_dialog.present()
            return
        self._pref_dialog = PreferencesDialog(self._settings, self._catalog, self)
        self._pref_dialog.connect("close-request", self._on_preferences_closed)
        self._pref_dialog.present()

    def _on_preferences_closed(self, _dialog: Gtk.Window) -> bool:
        """Recalculates the timetable after the dialog closes; a failure is logged and never blocks closing."""
        self._pref_dialog = None
        try:
            self._refresh_times()
        except Exception as error:  # noqa: BLE001 - closing the dialog must always succeed
            logger.warning("Could not refresh the screen after preferences: %r", error)
        return False

    def _hide_after_notice(self) -> bool:
        """Hides the window once the background notice has been shown."""
        self.hide()
        return False

    def do_close_request(self) -> bool:
        """Handles the close button: quit if the background service runs, otherwise hide.

        With the service running, notifications continue without this process, so the application
        quits. Otherwise the application must keep running to send them: the first close explains this
        in a toast and hides the window shortly after; later closes hide it at once. Always returns
        ``True`` because hiding or quitting is handled here.
        """
        if service_is_active():
            self.get_application().quit()
            return True

        if not self._close_notice_shown:
            self._close_notice_shown = True
            self._show_toast(tr("window.toast.background_notice"))
            GLib.timeout_add(BACKGROUND_HIDE_DELAY_MS, self._hide_after_notice)
            return True

        self.hide()
        return True
