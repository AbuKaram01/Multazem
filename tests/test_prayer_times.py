# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from multazem.core.calculation import CalculationMethod
from multazem.core.egypt_cities import EGYPT_CITIES
from multazem.core.prayer_times import CalculationParams, calculate_prayer_times
from multazem.core.prayers import FRIDAY, OBLIGATORY_PRAYERS, Prayer
from multazem.core.schedule import PrayerSchedule
from multazem.core.timeutil import local_now, wall_to_timestamp
from multazem.i18n import LocalizedError

CAIRO = (30.0444, 31.2357, "Africa/Cairo")


def hhmm(dt):
    return dt.strftime("%H:%M")


def test_cairo_regression_values():
    t = calculate_prayer_times(*CAIRO, date(2026, 10, 9), CalculationMethod.EGYPTIAN, 1)
    assert [hhmm(x) for x in (t.fajr, t.sunrise, t.dhuhr, t.asr, t.maghrib, t.isha)] == [
        "05:27",
        "06:53",
        "12:42",
        "16:01",
        "18:31",
        "19:48",
    ]
    assert t.tz_name == "Africa/Cairo" and t.date == date(2026, 10, 9)


@pytest.mark.parametrize("d", [date(2026, 3, 20), date(2026, 6, 21), date(2026, 9, 23), date(2026, 12, 21)])
@pytest.mark.parametrize("method", list(CalculationMethod))
def test_order_is_sane_for_every_egyptian_city(d, method):
    for _arabic, name, lat, lon in EGYPT_CITIES:
        t = calculate_prayer_times(lat, lon, "Africa/Cairo", d, method, 1)
        sequence = list(t.as_dict().values())
        assert sequence == sorted(sequence) and len(set(sequence)) == 6, (name, d, method)
        assert all(moment.tzinfo is None for moment in sequence)


def test_timetable_is_keyed_by_prayer_in_daily_order():
    t = calculate_prayer_times(*CAIRO, date(2026, 10, 9))
    assert list(t.as_dict()) == list(Prayer)


def test_hanafi_asr_is_later():
    standard = calculate_prayer_times(*CAIRO, date(2026, 10, 9), CalculationMethod.EGYPTIAN, 1)
    hanafi = calculate_prayer_times(*CAIRO, date(2026, 10, 9), CalculationMethod.EGYPTIAN, 2)
    assert hanafi.asr > standard.asr and hanafi.fajr == standard.fajr


@pytest.mark.parametrize(
    "lat,lon,tz",
    [
        (float("nan"), 31, "UTC"),
        (30, float("inf"), "UTC"),
        (91, 0, "UTC"),
        (0, -181, "UTC"),
        (30, 31, ""),
        (30, 31, "Foo/Bar"),
        (30, 31, "../../etc/passwd"),
        (30, 31, "/etc/passwd"),
    ],
)
def test_invalid_input_is_valueerror(lat, lon, tz):
    with pytest.raises(ValueError):
        calculate_prayer_times(lat, lon, tz, date(2026, 10, 9))


def test_errors_are_localizable():
    with pytest.raises(LocalizedError) as raised:
        calculate_prayer_times(91, 0, "UTC", date(2026, 10, 9))
    error = raised.value
    assert "Latitude" in str(error)
    assert "خط العرض" in error.localized("ar")


@pytest.mark.parametrize(
    "lat,lon,tz,d",
    [
        (69.65, 18.96, "Europe/Oslo", date(2026, 6, 21)),
        (69.65, 18.96, "Europe/Oslo", date(2026, 12, 21)),
        (78.22, 15.65, "Arctic/Longyearbyen", date(2026, 6, 21)),
        (90.0, 0.0, "UTC", date(2026, 6, 21)),
    ],
)
def test_polar_regions_raise_valueerror_not_runtimeerror(lat, lon, tz, d):
    with pytest.raises(ValueError, match="Cannot calculate prayer times"):
        calculate_prayer_times(lat, lon, tz, d, CalculationMethod.MUSLIM_WORLD_LEAGUE)


def test_high_latitude_summer_has_distinct_sensible_times():
    t = calculate_prayer_times(
        51.5, -0.12, "Europe/London", date(2026, 6, 21), CalculationMethod.MUSLIM_WORLD_LEAGUE, 1
    )
    assert t.fajr < t.sunrise < t.dhuhr < t.asr < t.maghrib < t.isha
    assert hhmm(t.fajr) != hhmm(t.isha)


@pytest.mark.parametrize(
    "lat,lon,tz",
    [
        (31.2, 29.9, "Africa/Cairo"),
        (24.71, 46.67, "Asia/Riyadh"),
        (48.0, 2.35, "Europe/Paris"),
        (-33.9, 18.4, "Africa/Johannesburg"),
    ],
)
def test_places_at_or_below_48_degrees_are_unchanged_by_the_high_latitude_fix(lat, lon, tz):
    from adhanpy.calculation import CalculationMethod as AdhanMethod
    from adhanpy.calculation.CalculationParameters import CalculationParameters
    from adhanpy.calculation.PrayerAdjustments import PrayerAdjustments
    from adhanpy.PrayerTimes import PrayerTimes as RawPrayerTimes

    day = date(2026, 6, 21)
    params = CalculationParameters(method=AdhanMethod.MUSLIM_WORLD_LEAGUE)
    params.adjustments = PrayerAdjustments(dhuhr=-1)
    raw = RawPrayerTimes((lat, lon), day, calculation_parameters=params, time_zone=ZoneInfo(tz))
    ours = calculate_prayer_times(lat, lon, tz, day, CalculationMethod.MUSLIM_WORLD_LEAGUE, 1)
    assert ours.fajr == raw.fajr.replace(tzinfo=None) and ours.isha == raw.isha.replace(tzinfo=None)


def test_umm_al_qura_isha_is_90_minutes_after_maghrib():
    t = calculate_prayer_times(24.71, 46.67, "Asia/Riyadh", date(2026, 10, 9), CalculationMethod.UMM_AL_QURA, 1)
    assert (t.isha - t.maghrib).total_seconds() == 90 * 60


def test_default_date_is_today_at_the_location_not_the_machine():
    places = {"Pacific/Kiritimati": (1.87, -157.4), "Pacific/Pago_Pago": (-14.27, -170.7)}
    for tz, (lat, lon) in places.items():
        t = calculate_prayer_times(lat, lon, tz)
        assert t.date == datetime.now(ZoneInfo(tz)).date()


def test_next_prayer_progression():
    t = calculate_prayer_times(*CAIRO, date(2026, 10, 9))

    def at(hour, minute):
        return datetime(2026, 10, 9, hour, minute)

    assert t.next_prayer(at(0, 0))[0] is Prayer.FAJR
    assert t.next_prayer(at(5, 30))[0] is Prayer.DHUHR
    assert t.next_prayer(at(12, 41))[0] is Prayer.DHUHR
    assert t.next_prayer(at(12, 42))[0] is Prayer.ASR
    assert t.next_prayer(at(19, 48)) is None
    assert t.next_prayer(at(23, 59)) is None


def test_sunrise_is_the_only_non_prayer():
    assert [p for p in Prayer if not p.is_prayer] == [Prayer.SUNRISE]
    assert Prayer.SUNRISE not in OBLIGATORY_PRAYERS and len(OBLIGATORY_PRAYERS) == 5


def test_dhuhr_is_labelled_jumuah_only_on_fridays():
    friday, thursday, saturday = date(2026, 10, 9), date(2026, 10, 8), date(2026, 10, 10)
    assert friday.weekday() == FRIDAY
    assert Prayer.DHUHR.label_key_on(friday) == "prayer.jumuah"
    assert Prayer.DHUHR.label_key_on(thursday) == Prayer.DHUHR.label_key == "prayer.dhuhr"
    assert Prayer.DHUHR.label_key_on(saturday) == "prayer.dhuhr"


def test_no_other_entry_is_renamed_on_fridays():
    friday = date(2026, 10, 9)
    for prayer in Prayer:
        if prayer is not Prayer.DHUHR:
            assert prayer.label_key_on(friday) == prayer.label_key


def test_exactly_the_fridays_of_two_years_are_recognised():
    day, fridays = date(2026, 1, 1), 0
    while day < date(2028, 1, 1):
        is_friday = Prayer.DHUHR.label_key_on(day) == "prayer.jumuah"
        assert is_friday == (day.weekday() == FRIDAY)
        fridays += is_friday
        day += timedelta(days=1)
    assert fridays == 105


def test_next_prayer_still_skips_sunrise_now_that_it_can_notify():
    t = calculate_prayer_times(*CAIRO, date(2026, 10, 9))
    sunrise = t.sunrise
    assert t.next_prayer(sunrise - timedelta(minutes=1))[0] is Prayer.DHUHR


def test_wall_to_timestamp_dst_spring_gap_does_not_raise():
    ts = wall_to_timestamp(datetime(2026, 3, 8, 2, 30), "America/New_York")
    assert isinstance(ts, float)


def test_wall_to_timestamp_is_true_elapsed_time_across_fall_back():
    a = wall_to_timestamp(datetime(2026, 11, 1, 0, 30), "America/New_York")
    b = wall_to_timestamp(datetime(2026, 11, 1, 3, 30), "America/New_York")
    assert b - a == 4 * 3600


def test_local_now_follows_the_location(monkeypatch):
    monkeypatch.setenv("TZ", "Pacific/Pago_Pago")
    time.tzset()
    try:
        cairo = local_now("Africa/Cairo")
        expected = datetime.now(ZoneInfo("Africa/Cairo")).replace(tzinfo=None)
        assert abs((cairo - expected).total_seconds()) < 5
    finally:
        monkeypatch.undo()
        time.tzset()


def test_calculation_params_match_the_function():
    params = CalculationParams(*CAIRO, method=CalculationMethod.EGYPTIAN)
    assert params.prayer_times(date(2026, 10, 9)) == calculate_prayer_times(
        *CAIRO, date(2026, 10, 9), CalculationMethod.EGYPTIAN, 1
    )


def test_schedule_points_at_tomorrows_fajr_after_isha_and_caches_it():
    schedule = PrayerSchedule(CalculationParams(*CAIRO))
    late = datetime.combine(schedule.today.date, datetime.max.time().replace(microsecond=0))
    upcoming = schedule.next_prayer(late)
    assert upcoming.prayer is Prayer.FAJR and upcoming.when.date() > schedule.today.date
    assert schedule.tomorrow() is schedule.tomorrow()


def test_schedule_without_a_tomorrow_returns_none_after_isha(monkeypatch):
    schedule = PrayerSchedule(CalculationParams(*CAIRO))
    monkeypatch.setattr(
        CalculationParams, "prayer_times", lambda self, day=None: (_ for _ in ()).throw(ValueError("polar"))
    )
    late = datetime.combine(schedule.today.date, datetime.max.time().replace(microsecond=0))
    assert schedule.next_prayer(late) is None


def test_seconds_until_is_never_negative_and_uses_absolute_time():
    schedule = PrayerSchedule(CalculationParams(*CAIRO))
    moment = schedule.today.dhuhr
    ts = wall_to_timestamp(moment, "Africa/Cairo")
    assert schedule.seconds_until(moment, now_ts=ts - 90) == 90
    assert schedule.seconds_until(moment, now_ts=ts + 90) == 0
