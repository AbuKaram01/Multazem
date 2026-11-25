# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Shared constants and helpers of the scheduler tests.

The scenarios use Cairo time on Saturday 2026-10-10 (``D``) unless a test says otherwise, with
the default Egyptian calculation; the notification texts are the English ones.
"""

CAIRO = "Africa/Cairo"
D = (2026, 10, 10)
NEXT_DAY = (2026, 10, 11)
FRIDAY = (2026, 10, 9)

DHUHR = "Dhuhr prayer time"
ASR = "Asr prayer time"
FAJR = "Fajr prayer time"
JUMUAH = "Jumu'ah prayer time"
SUNRISE = "Sunrise"
SUNRISE_REMINDER = "Reminder \u2013 Sunrise"
DHUHR_REMINDER = "Reminder \u2013 Dhuhr prayer"
FAJR_REMINDER = "Reminder \u2013 Fajr prayer"


def fire_dhuhr(eng, clock, day, *, at=(12, 41, 59)):
    """Moves the clock to just before Dhuhr and ticks past it so that its notification fires.

    Args:
        eng: The scheduler under test.
        clock: The fake clock the scheduler reads.
        day: ``(year, month, day)`` of the Dhuhr to fire.
        at: ``(hour, minute, second)`` to start from, shortly before that day's Dhuhr.
    """
    clock.set_wall(CAIRO, *day, *at)
    clock.advance(eng.tick())
    eng.tick()
