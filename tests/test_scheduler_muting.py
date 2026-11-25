# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Muting prayers: a muted entry gets neither its notification nor its reminder, also when muted by another process."""

from datetime import datetime

from multazem.core.prayers import Prayer
from multazem.core.timeutil import wall_to_timestamp
from multazem.services.settings import Settings

from scheduler_support import ASR, CAIRO, DHUHR, NEXT_DAY, D


def test_a_muted_prayer_gets_neither_its_notification_nor_its_reminder(make, clock):
    eng, rec = make()
    eng._settings.set_prayer_enabled(Prayer.DHUHR, False)
    clock.set_wall(CAIRO, *D, 12, 31, 59)
    clock.advance(eng.tick())
    clock.set_wall(CAIRO, *D, 12, 41, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == []
    clock.set_wall(CAIRO, *D, 15, 59, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == [ASR]


def test_each_prayer_can_be_muted_independently(make, clock):
    eng, rec = make()
    st = eng._settings
    for prayer in (Prayer.FAJR, Prayer.ASR, Prayer.ISHA):
        st.set_prayer_enabled(prayer, False)
    start = clock.set_wall(CAIRO, *D, 0, 0, 0)
    end = wall_to_timestamp(datetime(*NEXT_DAY, 0, 0), CAIRO)
    while clock.ts < end:
        clock.advance(eng.tick())
    names = {t.replace("Reminder \u2013 ", "").replace(" prayer time", "").replace(" prayer", "") for t in rec.titles}
    assert names == {"Sunrise", "Dhuhr", "Maghrib"}
    assert len(rec.calls) == 6 and start < clock.ts


def test_muting_from_another_process_takes_effect_live(make, clock, settings_path):
    eng, rec = make()
    gui = Settings(settings_path)
    clock.set_wall(CAIRO, *D, 12, 41, 0)
    eng.tick()
    gui.set_prayer_enabled(Prayer.DHUHR, False)
    clock.set_wall(CAIRO, *D, 12, 42, 0.5)
    eng.tick()
    assert rec.titles == []
    gui.set_prayer_enabled(Prayer.DHUHR, True)
    clock.set_wall(CAIRO, *D, 12, 42, 1.5)
    eng.tick()
    assert rec.titles == [DHUHR]
