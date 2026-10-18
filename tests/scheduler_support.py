# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

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
    clock.set_wall(CAIRO, *day, *at)
    clock.advance(eng.tick())
    eng.tick()
