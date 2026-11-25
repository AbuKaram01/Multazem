# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The language of notification texts: configured language, reminders and changes made by another process."""

from multazem.i18n import set_language
from multazem.services.settings import Settings

from scheduler_support import CAIRO, DHUHR, D


def test_notification_text_follows_the_configured_language(make, clock):
    eng, rec = make()
    eng._settings.language = "ar"
    clock.set_wall(CAIRO, *D, 12, 41, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert [c[1] for c in rec.calls] == ["حان وقت الظهر"]
    assert rec.calls[0][2] == "الساعة 12:42 \u2013 حان الآن وقت صلاة الظهر"


def test_reminder_text_is_localized_too(make, clock):
    eng, rec = make()
    eng._settings.language = "ar"
    clock.set_wall(CAIRO, *D, 12, 31, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == ["تذكير \u2013 صلاة الظهر"]
    assert rec.calls[0][2] == "باقي 10 دقيقة على صلاة الظهر"


def test_notifications_use_the_settings_language_not_the_process_language(make, clock):
    set_language("ar")
    eng, rec = make()
    assert eng._settings.language == "en"
    clock.set_wall(CAIRO, *D, 12, 41, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == [DHUHR]


def test_language_changed_by_another_process_applies_to_the_next_notification(make, clock, settings_path):
    eng, rec = make()
    gui = Settings(settings_path)
    clock.set_wall(CAIRO, *D, 12, 41, 0)
    eng.tick()
    gui.language = "ar"
    clock.set_wall(CAIRO, *D, 12, 42, 1)
    eng.tick()
    assert rec.titles == ["حان وقت الظهر"]
