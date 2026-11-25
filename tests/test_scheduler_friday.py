# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The scheduler's wording on Fridays: Dhuhr is announced as Jumu'ah and keeps its everyday name on other days."""

import time
import zoneinfo
from datetime import date, datetime

import pytest

from multazem.core.calculation import CalculationMethod
from multazem.core.prayer_times import calculate_prayer_times
from multazem.core.prayers import Prayer
from multazem.core.timeutil import wall_to_timestamp

from platform_support import needs_tzset
from scheduler_support import ASR, CAIRO, DHUHR, FAJR, FRIDAY, JUMUAH, NEXT_DAY, D, fire_dhuhr


def test_dhuhr_is_announced_as_jumuah_on_friday(make, clock):
    eng, rec = make()
    fire_dhuhr(eng, clock, FRIDAY)
    assert rec.titles == [JUMUAH]
    assert rec.calls[0][2] == "It is 12:42 – time for Jumu'ah prayer"


def test_friday_reminder_says_jumuah_too(make, clock):
    eng, rec = make()
    fire_dhuhr(eng, clock, FRIDAY, at=(12, 31, 59))
    assert rec.titles == ["Reminder – Jumu'ah prayer"]
    assert rec.calls[0][2] == "10 min until Jumu'ah prayer"


def test_friday_notification_is_arabic_when_the_language_is_arabic(make, clock):
    eng, rec = make()
    eng._settings.language = "ar"
    fire_dhuhr(eng, clock, FRIDAY)
    assert rec.titles == ["حان وقت الجمعة"]
    assert rec.calls[0][2] == "الساعة 12:42 – حان الآن وقت صلاة الجمعة"
    fire_dhuhr(eng, clock, FRIDAY, at=(12, 31, 59))
    clock.set_wall(CAIRO, *NEXT_DAY, 12, 31, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles[-1] == "تذكير – صلاة الظهر"


@pytest.mark.parametrize("day", [(2026, 10, 8), (2026, 10, 10), (2026, 10, 11)])
def test_dhuhr_keeps_its_everyday_name_on_every_other_weekday(make, clock, day):
    eng, rec = make()
    dhuhr = calculate_prayer_times(30.0444, 31.2357, CAIRO, date(*day), CalculationMethod.EGYPTIAN).dhuhr
    fire_dhuhr(eng, clock, day, at=(dhuhr.hour, dhuhr.minute - 1, 59))
    assert rec.titles == [DHUHR]


def test_only_dhuhr_is_renamed_on_friday(make, clock):
    eng, rec = make()
    start = clock.set_wall(CAIRO, *FRIDAY, 0, 0, 0)
    end = wall_to_timestamp(datetime(*D, 0, 0), CAIRO)
    while clock.ts < end:
        clock.advance(eng.tick())
    prayer_titles = [t for t in rec.titles if t.endswith(" prayer time")]
    assert prayer_titles == [FAJR, JUMUAH, ASR, "Maghrib prayer time", "Isha prayer time"]
    assert DHUHR not in rec.titles and start < clock.ts


def test_the_friday_switch_is_the_dhuhr_switch(make, clock):
    eng, rec = make()
    eng._settings.set_prayer_enabled(Prayer.DHUHR, False)
    fire_dhuhr(eng, clock, FRIDAY)
    fire_dhuhr(eng, clock, FRIDAY, at=(12, 31, 59))
    assert rec.titles == []


@needs_tzset
def test_friday_is_decided_by_the_date_at_the_location_not_on_the_machine(make, clock, monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        eng, rec = make()
        st = eng._settings
        st.latitude, st.longitude, st.timezone_name = -36.8485, 174.7633, "Pacific/Auckland"
        st.reminder_enabled = False
        dhuhr = calculate_prayer_times(
            -36.8485, 174.7633, "Pacific/Auckland", date(*FRIDAY), CalculationMethod.EGYPTIAN
        ).dhuhr
        ts = wall_to_timestamp(dhuhr, "Pacific/Auckland")
        assert datetime.fromtimestamp(ts, tz=zoneinfo.ZoneInfo("America/New_York")).weekday() == 3
        clock.ts = ts - 0.5
        eng.tick()
        clock.ts = ts + 0.01
        eng.tick()
        assert JUMUAH in rec.titles
    finally:
        monkeypatch.undo()
        time.tzset()


def test_friday_log_line_uses_the_jumuah_name(make, clock, capsys):
    eng, _ = make()
    clock.set_wall(CAIRO, *FRIDAY, 9, 0, 0)
    eng.tick()
    out = capsys.readouterr().out
    assert "2026-10-09" in out and "Jumu'ah 12:42" in out and "Dhuhr" not in out
