# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Sunrise notifications: their own wording and reminder, in both languages, independent of the prayers."""

from datetime import datetime

from multazem.core.prayers import Prayer
from multazem.core.timeutil import wall_to_timestamp
from multazem.services.settings import Settings

from scheduler_support import CAIRO, DHUHR, SUNRISE, SUNRISE_REMINDER, D, fire_dhuhr


def test_sunrise_notification_fires_at_the_right_second_with_its_own_wording(make, clock):
    eng, rec = make()
    clock.set_wall(CAIRO, *D, 6, 53, 59)
    wait = eng.tick()
    assert SUNRISE not in rec.titles and 0 < wait <= 1.02
    clock.advance(wait)
    eng.tick()
    eng.tick()
    assert rec.titles == [SUNRISE]
    assert rec.calls[0][2] == "It is 06:54 – the sun is rising now"
    assert rec.calls[0][3] == "daytime-sunrise-symbolic"
    assert 0 <= rec.calls[0][0] - wall_to_timestamp(datetime(*D, 6, 54), CAIRO) < 0.1


def test_sunrise_reminder_fires_n_minutes_before_and_mentions_the_end_of_fajr(make, clock):
    eng, rec = make()
    clock.set_wall(CAIRO, *D, 6, 43, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == [SUNRISE_REMINDER]
    assert rec.calls[0][2] == "Sunrise in 10 min – the time for Fajr is about to end"


def test_sunrise_is_announced_in_arabic_when_the_language_is_arabic(make, clock):
    eng, rec = make()
    eng._settings.language = "ar"
    clock.set_wall(CAIRO, *D, 6, 43, 59)
    clock.advance(eng.tick())
    eng.tick()
    clock.set_wall(CAIRO, *D, 6, 53, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == ["تذكير – الشروق", "الشروق"]
    assert rec.calls[0][2] == "باقي 10 دقيقة على الشروق – وقت صلاة الفجر على وشك الانتهاء"
    assert rec.calls[1][2] == "الساعة 06:54 – شروق الشمس الآن"


def test_a_muted_sunrise_gets_neither_notification_nor_reminder_and_prayers_are_unaffected(make, clock):
    eng, rec = make()
    eng._settings.set_prayer_enabled(Prayer.SUNRISE, False)
    for moment in ((6, 43, 59), (6, 53, 59)):
        clock.set_wall(CAIRO, *D, *moment)
        clock.advance(eng.tick())
        eng.tick()
    assert rec.titles == []
    fire_dhuhr(eng, clock, D)
    assert rec.titles == [DHUHR]


def test_muting_a_prayer_does_not_mute_sunrise(make, clock):
    eng, rec = make()
    eng._settings.set_prayer_enabled(Prayer.FAJR, False)
    clock.set_wall(CAIRO, *D, 6, 53, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == [SUNRISE]


def test_sunrise_switch_changed_by_another_process_takes_effect_live(make, clock, settings_path):
    eng, rec = make()
    gui = Settings(settings_path)
    clock.set_wall(CAIRO, *D, 6, 53, 0)
    eng.tick()
    gui.set_prayer_enabled(Prayer.SUNRISE, False)
    clock.set_wall(CAIRO, *D, 6, 54, 0.5)
    eng.tick()
    assert rec.titles == []
    gui.set_prayer_enabled(Prayer.SUNRISE, True)
    clock.set_wall(CAIRO, *D, 6, 54, 1.5)
    eng.tick()
    assert rec.titles == [SUNRISE]


def test_sunrise_follows_the_global_notification_switches(make, clock):
    eng, rec = make()
    eng._settings.notify_on_prayer = False
    eng._settings.reminder_enabled = False
    clock.set_wall(CAIRO, *D, 6, 53, 59)
    eng.tick()
    clock.set_wall(CAIRO, *D, 6, 54, 1)
    eng.tick()
    assert rec.calls == []
    eng._settings.notify_on_prayer = True
    clock.set_wall(CAIRO, *D, 6, 54, 2)
    eng.tick()
    assert rec.titles == [SUNRISE]
