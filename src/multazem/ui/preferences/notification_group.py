# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

import threading
from collections.abc import Callable

from gi.repository import Adw, GLib, Gtk

from ...i18n import tr
from ...services.notifications import send_notification
from ...services.settings import MIN_REMINDER_MINUTES, Settings
from ..bindings import bind_spin_row, bind_switch_row

_MAX_REMINDER_MINUTES_IN_UI = 60
_TEST_ICON = "dialog-information-symbolic"


class NotificationGroup(Adw.PreferencesGroup):
    def __init__(self, settings: Settings, show_toast: Callable[[str], None]) -> None:
        super().__init__(title=tr("prefs.notifications.title"))
        self._show_toast = show_toast

        notify_row = Adw.SwitchRow(title=tr("prefs.notifications.at_prayer"))
        bind_switch_row(notify_row, settings, "notify_on_prayer")
        self.add(notify_row)

        reminder_row = Adw.SwitchRow(title=tr("prefs.notifications.reminder"))
        bind_switch_row(reminder_row, settings, "reminder_enabled")
        self.add(reminder_row)

        minutes_row = Adw.SpinRow.new_with_range(MIN_REMINDER_MINUTES, _MAX_REMINDER_MINUTES_IN_UI, 1)
        minutes_row.set_title(tr("prefs.notifications.minutes.title"))
        minutes_row.set_subtitle(tr("prefs.notifications.minutes.subtitle"))
        minutes_row.set_digits(0)
        bind_spin_row(minutes_row, settings, "reminder_minutes", convert=int)
        self.add(minutes_row)

        self.add(self._build_test_row())

    def _build_test_row(self) -> Adw.ActionRow:
        row = Adw.ActionRow(title=tr("prefs.test.title"), subtitle=tr("prefs.test.subtitle"))
        button = Gtk.Button(label=tr("prefs.test.button"))
        button.set_valign(Gtk.Align.CENTER)
        button.add_css_class("flat")
        button.connect("clicked", self._on_test_clicked)
        row.add_suffix(button)
        row.set_activatable_widget(button)
        return row

    def _on_test_clicked(self, button: Gtk.Button) -> None:
        button.set_sensitive(False)

        def work() -> None:
            ok, detail = send_notification(
                tr("prefs.test.notification.title"),
                tr("prefs.test.notification.body"),
                _TEST_ICON,
            )
            GLib.idle_add(lambda: (finish(ok, detail), False)[1])

        def finish(ok: bool, detail: str) -> None:
            button.set_sensitive(True)
            if ok:
                self._show_toast(tr("prefs.test.sent"))
            else:
                self._show_toast(tr("prefs.test.failed", detail=detail))

        threading.Thread(target=work, daemon=True).start()
