# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""When the notification scheduler fires: exact timing, reminders, grace periods, suspend, time zones and errors.

All tests drive the scheduler with a fake clock and a recording notifier (see ``conftest.py``).
"""

import time
from datetime import date, datetime, timedelta

import pytest

from multazem.core.calculation import CalculationMethod
from multazem.core.prayer_times import calculate_prayer_times
from multazem.core.timeutil import wall_to_timestamp
from multazem.i18n import tr
from multazem.services.settings import Settings

from platform_support import needs_tzset
from scheduler_support import (
    ASR,
    CAIRO,
    DHUHR,
    DHUHR_REMINDER,
    FAJR,
    FAJR_REMINDER,
    JUMUAH,
    NEXT_DAY,
    SUNRISE,
    SUNRISE_REMINDER,
    D,
)


def test_prayer_fires_once_at_the_right_second(make, clock):
    eng, rec = make()
    clock.set_wall(CAIRO, *D, 12, 41, 59)
    wait = eng.tick()
    assert DHUHR not in rec.titles and 0 < wait <= 1.02
    clock.advance(wait)
    eng.tick()
    eng.tick()
    assert rec.titles == [DHUHR]
    assert 0 <= rec.calls[0][0] - wall_to_timestamp(datetime(*D, 12, 42), CAIRO) < 0.1


def test_reminder_fires_n_minutes_before(make, clock):
    eng, rec = make()
    clock.set_wall(CAIRO, *D, 12, 31, 59)
    wait = eng.tick()
    clock.advance(wait)
    eng.tick()
    assert rec.titles == [DHUHR_REMINDER] and "10 min until Dhuhr" in rec.calls[0][2]


@pytest.mark.parametrize(
    "h,m,s,expected_fired", [(12, 42, 30, True), (12, 43, 29, True), (12, 43, 31, False), (12, 50, 0, False)]
)
def test_stale_events_are_skipped_but_events_within_grace_fire(make, clock, h, m, s, expected_fired):
    eng, rec = make()
    clock.set_wall(CAIRO, *D, h, m, s)
    eng.tick()
    assert (DHUHR in rec.titles) is expected_fired
    assert not any(t in rec.titles for t in (FAJR, FAJR_REMINDER, SUNRISE, SUNRISE_REMINDER))


def test_suspend_does_not_swallow_later_notifications(make, clock):
    """Regression test for the old ``threading.Timer`` engine.

    After a suspend every timer was delayed by the sleep duration, so all later notifications were
    dropped as "stale".
    """
    eng, rec = make()
    clock.set_wall(CAIRO, *D, 12, 0, 0)
    assert eng.tick() <= eng.MAX_SLEEP
    clock.set_wall(CAIRO, *D, 14, 0, 0)
    eng.tick()
    assert DHUHR not in rec.titles
    clock.set_wall(CAIRO, *D, 15, 59, 59)
    wait = eng.tick()
    clock.advance(wait)
    eng.tick()
    assert rec.titles.count(ASR) == 1


@needs_tzset
def test_system_timezone_is_irrelevant(make, clock, monkeypatch):
    monkeypatch.setenv("TZ", "America/New_York")
    time.tzset()
    try:
        eng, rec = make()
        clock.set_wall(CAIRO, *D, 12, 41, 59)
        clock.advance(eng.tick())
        eng.tick()
        assert rec.titles == [DHUHR]
    finally:
        monkeypatch.undo()
        time.tzset()


def test_dst_change_between_now_and_the_event(make, clock):
    eng, rec = make()
    eng._settings.latitude, eng._settings.longitude = 51.5, -0.12
    eng._settings.timezone_name = "Europe/London"
    eng._settings.calculation_method = CalculationMethod.MUSLIM_WORLD_LEAGUE
    eng._settings.reminder_enabled = False
    day = date(2026, 3, 29)
    fajr = calculate_prayer_times(51.5, -0.12, "Europe/London", day, CalculationMethod.MUSLIM_WORLD_LEAGUE).fajr
    ts = wall_to_timestamp(fajr, "Europe/London")
    naive = (fajr - datetime(2026, 3, 29, 0, 30)).total_seconds()
    assert ts - wall_to_timestamp(datetime(2026, 3, 29, 0, 30), "Europe/London") == naive - 3600
    clock.ts = ts - 0.5
    eng.tick()
    assert rec.calls == []
    clock.ts = ts + 0.01
    eng.tick()
    assert rec.titles == [FAJR]


def test_disabled_notifications_then_enabled_later(make, clock):
    eng, rec = make()
    st = eng._settings
    st.notify_on_prayer = False
    st.reminder_enabled = False
    clock.set_wall(CAIRO, *D, 12, 41, 0)
    assert eng.tick() == eng.MAX_SLEEP
    clock.set_wall(CAIRO, *D, 12, 43, 0)
    eng.tick()
    assert rec.calls == []
    st.notify_on_prayer = True
    clock.set_wall(CAIRO, *D, 15, 59, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == [ASR]


def test_reminder_minutes_change_takes_effect(make, clock):
    eng, rec = make()
    clock.set_wall(CAIRO, *D, 12, 20, 0)
    eng.tick()
    eng._settings.reminder_minutes = 5
    clock.set_wall(CAIRO, *D, 12, 36, 59)
    clock.advance(eng.tick())
    eng.tick()
    assert rec.titles == [DHUHR_REMINDER] and "5 min until Dhuhr" in rec.calls[0][2]


def test_settings_changed_by_another_process_are_picked_up(make, clock, settings_path):
    eng, rec = make()
    gui = Settings(settings_path)
    clock.set_wall(CAIRO, *D, 9, 0, 0)
    eng.tick()
    assert eng._calc_key.latitude == pytest.approx(30.0444)
    gui.latitude, gui.longitude, gui.timezone_name = 21.4225, 39.8262, "Asia/Riyadh"
    gui.reminder_enabled = False
    eng.tick()
    assert eng._calc_key.latitude == pytest.approx(21.4225) and eng._calc_key.timezone == "Asia/Riyadh"
    mecca_dhuhr = calculate_prayer_times(21.4225, 39.8262, "Asia/Riyadh", date(*D), CalculationMethod.EGYPTIAN).dhuhr
    ts = wall_to_timestamp(mecca_dhuhr, "Asia/Riyadh")
    clock.ts = ts - 0.5
    eng.tick()
    clock.ts = ts + 0.01
    eng.tick()
    assert rec.titles == [DHUHR] and rec.calls[0][0] == ts + 0.01


def test_invalid_timezone_at_runtime_does_not_kill_scheduling(make, clock, capsys):
    eng, _ = make()
    clock.set_wall(CAIRO, *D, 12, 0, 0)
    eng._settings._data["timezone_name"] = "Nope/Zone"
    assert eng.tick() == eng.ERROR_RETRY
    assert eng.tick() == eng.ERROR_RETRY
    assert capsys.readouterr().err.count("Invalid settings") == 1
    eng._settings._data["timezone_name"] = CAIRO
    assert eng.tick() <= eng.MAX_SLEEP


def test_polar_location_does_not_kill_scheduling(make, clock):
    eng, _ = make()
    eng._settings.latitude, eng._settings.longitude, eng._settings.timezone_name = 88.0, 0.0, "UTC"
    clock.set_wall("UTC", *D, 12, 0, 0)
    assert eng.tick() == eng.ERROR_RETRY
    eng._settings.latitude = 30.0
    assert eng.tick() <= eng.MAX_SLEEP


def test_failing_notifier_does_not_spin_or_stop(make, clock):
    eng, _ = make()
    boom = []

    def bad(*a):
        boom.append(a)
        raise RuntimeError("notify-send exploded")

    eng._notify = bad
    clock.set_wall(CAIRO, *D, 12, 42, 5)
    wait = eng.tick()
    assert len(boom) == 1 and wait >= 0.05
    eng.tick()
    assert len(boom) == 1


def test_fajr_reminder_that_falls_on_the_previous_day_is_not_missed(make, clock):
    eng, rec = make()
    eng._settings.reminder_minutes = 400
    fajr_tomorrow = calculate_prayer_times(30.0444, 31.2357, CAIRO, date(*NEXT_DAY), CalculationMethod.EGYPTIAN).fajr
    ts = wall_to_timestamp(fajr_tomorrow - timedelta(minutes=400), CAIRO)
    assert (fajr_tomorrow - timedelta(minutes=400)).date() == date(*D)
    clock.ts = ts - 0.5
    eng.tick()
    clock.ts = ts + 0.01
    eng.tick()
    assert FAJR_REMINDER in rec.titles and "400 min until Fajr" in rec.calls[-1][2]


def test_midnight_rollover_and_no_duplicates_across_days(make, clock):
    eng, rec = make()
    eng._settings.reminder_enabled = False
    clock.set_wall(CAIRO, *D, 23, 59, 50)
    eng.tick()
    clock.set_wall(CAIRO, *NEXT_DAY, 0, 0, 5)
    eng.tick()
    assert date(*D) not in eng._times
    fajr = calculate_prayer_times(30.0444, 31.2357, CAIRO, date(*NEXT_DAY), CalculationMethod.EGYPTIAN).fajr
    ts = wall_to_timestamp(fajr, CAIRO)
    clock.ts = ts - 0.5
    eng.tick()
    clock.ts = ts + 0.01
    eng.tick()
    eng.tick()
    assert rec.titles == [FAJR]


def test_clock_going_backwards_never_refires(make, clock):
    eng, rec = make()
    clock.set_wall(CAIRO, *D, 12, 42, 1)
    eng.tick()
    clock.set_wall(CAIRO, *D, 12, 41, 50)
    eng.tick()
    clock.set_wall(CAIRO, *D, 12, 42, 5)
    eng.tick()
    assert rec.titles.count(DHUHR) == 1


@pytest.mark.parametrize("remaining,expected", [(7200, 30.0), (100, 30.0), (10, 5.0), (3, 1.5), (0.4, 0.41)])
def test_wait_is_adaptive_and_bounded(make, clock, remaining, expected):
    eng, _ = make()
    eng._settings.reminder_enabled = False
    ts = wall_to_timestamp(datetime(*D, 12, 42), CAIRO)
    clock.ts = ts - remaining
    wait = eng.tick()
    assert wait == pytest.approx(expected, abs=0.011) if remaining < 60 else wait == expected


def _expected_notifications(first_day, days):
    """(title, timestamp) of every notification and reminder the scheduler owes over ``days`` days."""
    expected = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        times = calculate_prayer_times(30.0444, 31.2357, CAIRO, day, CalculationMethod.EGYPTIAN)
        for prayer, moment in times.as_dict().items():
            name = tr(prayer.label_key_on(day), language="en")
            if prayer.is_prayer:
                expected.append((f"{name} prayer time", wall_to_timestamp(moment, CAIRO)))
                reminder = f"Reminder \u2013 {name} prayer"
            else:
                expected.append((name, wall_to_timestamp(moment, CAIRO)))
                reminder = f"Reminder \u2013 {name}"
            expected.append((reminder, wall_to_timestamp(moment - timedelta(minutes=10), CAIRO)))
    return expected


def _run_until(eng, clock, end):
    """Tick the scheduler the way the timer would, until ``end``; returns how many ticks it took."""
    ticks = 0
    while clock.ts < end:
        wait = eng.tick()
        assert wait >= 0.01
        clock.advance(wait)
        ticks += 1
    return ticks


def test_three_day_simulation_precision_and_cpu_budget(make, clock):
    eng, rec = make()
    first_day = date(2026, 10, 8)
    start = clock.set_wall(CAIRO, first_day.year, first_day.month, first_day.day, 0, 0, 0)
    ticks = _run_until(eng, clock, wall_to_timestamp(datetime(2026, 10, 11, 0, 0), CAIRO))

    expected = _expected_notifications(first_day, days=3)
    fired = sorted((call[1], call[0]) for call in rec.calls)
    assert len(rec.calls) == 36 == len(expected)
    assert sum(title == JUMUAH for title, _ in expected) == 1
    for title, ts in sorted(expected, key=lambda item: item[1]):
        got = [t for (name, t) in fired if name == title and 0 <= t - ts < 1.0]
        assert len(got) == 1, (title, ts)
    assert ticks < 10_000
    assert start < clock.ts


def test_one_log_line_per_day_with_the_times_in_force(make, clock, capsys):
    eng, _ = make()
    clock.set_wall(CAIRO, *D, 9, 0, 0)
    for _ in range(5):
        eng.tick()
    out = capsys.readouterr().out
    assert out.count("[scheduler] 2026-10-10 (Africa/Cairo):") == 1
    assert "Sunrise 06:54" in out and "Dhuhr 12:42" in out
    clock.set_wall(CAIRO, *NEXT_DAY, 0, 0, 5)
    eng.tick()
    eng.tick()
    out = capsys.readouterr().out
    assert out.count("[scheduler] 2026-10-11 (Africa/Cairo):") == 1
    eng._settings.latitude, eng._settings.longitude, eng._settings.timezone_name = 21.4225, 39.8262, "Asia/Riyadh"
    eng.tick()
    assert "(Asia/Riyadh)" in capsys.readouterr().out
