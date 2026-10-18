# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path

from gi.repository import GLib

from ..core.prayer_times import CalculationParams, PrayerTimes
from ..core.prayers import Prayer
from ..core.timeutil import wall_to_timestamp, zone_for
from ..i18n import DEFAULT_LANGUAGE, tr
from ..logs import get_logger
from .notifications import DEFAULT_ICON, PRAYER_ICONS, send_notification
from .process_lock import ProcessLock
from .settings import Settings

logger = get_logger("scheduler")

Notifier = Callable[[str, str, str], object]

_HANDLED_RETENTION_DAYS = 2


class EventKind(Enum):
    PRAYER = "prayer"
    REMINDER = "reminder"


# Which message pair ("<key>.title" and "<key>.body") each kind of event uses; the flag says "it is sunrise".
MESSAGE_KEYS = {
    (EventKind.PRAYER, False): "notification.prayer",
    (EventKind.PRAYER, True): "notification.sunrise",
    (EventKind.REMINDER, False): "notification.reminder",
    (EventKind.REMINDER, True): "notification.sunrise_reminder",
}


@dataclass(frozen=True)
class _Event:
    when: datetime
    kind: EventKind
    prayer: Prayer
    minutes: int = 0

    @property
    def key(self) -> tuple:
        return (self.kind, self.prayer, self.when)


class NotificationScheduler:
    GRACE_SECONDS = 90
    MAX_SLEEP = 30.0
    LOCK_RETRY = 5.0
    ERROR_RETRY = 60.0
    TAKEOVER_GRACE = LOCK_RETRY + 1.0
    PRECISE_WAKE_WINDOW = 1.0
    WAKE_MARGIN = 0.01

    def __init__(
        self,
        settings: Settings,
        notify: Notifier = send_notification,
        now_ts: Callable[[], float] = time.time,
        lock_path: Path | None = None,
        threaded: bool = False,
    ) -> None:
        self._settings = settings
        self._notify = notify
        self._now_ts = now_ts
        self._lock = ProcessLock(lock_path)
        self._threaded = threaded
        self._running = False
        self._source: int | None = None
        self._times: dict[date, PrayerTimes] = {}
        self._calc_key: CalculationParams | None = None
        self._handled: set[tuple] = set()
        self._last_error: str | None = None
        self._logged_day: tuple | None = None

    def start(self) -> None:
        self._running = True
        self._arm(0.0)

    def refresh(self) -> None:
        if self._running:
            self._arm(0.0)

    def stop(self) -> None:
        self._running = False
        self._disarm()
        self._lock.release()

    @property
    def is_leader(self) -> bool:
        return self._lock.held

    def _arm(self, seconds: float) -> None:
        self._disarm()
        if self._running:
            self._source = GLib.timeout_add(max(1, int(seconds * 1000)), self._on_timeout)

    def _disarm(self) -> None:
        if self._source is not None:
            GLib.source_remove(self._source)
            self._source = None

    def _on_timeout(self) -> bool:
        self._source = None
        if not self._running:
            return False
        try:
            wait = self.tick()
        except Exception as error:  # noqa: BLE001 - the timer must keep running whatever goes wrong
            logger.error("Unexpected error: %r", error)
            wait = self.ERROR_RETRY
        self._arm(wait)
        return False

    def tick(self) -> float:
        try:
            self._settings.reload_if_changed()
        except Exception as error:  # noqa: BLE001 - a bad settings file must not stop the reminders
            self._log_once(logging.WARNING, f"Could not reload the settings: {error!r}")
        if not self._lock.acquire():
            return self.LOCK_RETRY
        try:
            wait = self._process()
            self._last_error = None
            return wait
        except ValueError as error:
            self._log_once(logging.WARNING, f"Invalid settings: {error}")
            return self.ERROR_RETRY
        except Exception as error:  # noqa: BLE001 - report it, then try again in a minute
            self._log_once(logging.ERROR, f"Error: {error!r}")
            return self.ERROR_RETRY

    def _log_once(self, level: int, message: str) -> None:
        if message != self._last_error:
            self._last_error = message
            logger.log(level, "%s", message)

    def _log_day(self, today: date, tz_name: str, times: PrayerTimes) -> None:
        marker = (today, self._calc_key)
        if self._logged_day == marker:
            return
        self._logged_day = marker
        parts = " | ".join(
            f"{tr(prayer.label_key_on(times.date), language=DEFAULT_LANGUAGE)} {moment.strftime('%H:%M')}"
            for prayer, moment in times.as_dict().items()
        )
        logger.info("%s (%s): %s", today.isoformat(), tz_name, parts)

    def _times_for(self, day: date) -> PrayerTimes:
        assert self._calc_key is not None
        if day not in self._times:
            self._times[day] = self._calc_key.prayer_times(day)
        return self._times[day]

    def _events(self, times: PrayerTimes) -> list[_Event]:
        settings = self._settings
        minutes = settings.reminder_minutes
        events: list[_Event] = []
        for prayer, moment in times.as_dict().items():
            if not settings.prayer_enabled(prayer):
                continue
            if settings.notify_on_prayer:
                events.append(_Event(moment, EventKind.PRAYER, prayer))
            if settings.reminder_enabled:
                events.append(_Event(moment - timedelta(minutes=minutes), EventKind.REMINDER, prayer, minutes))
        return events

    def _process(self) -> float:
        params = self._use_current_calculation()
        now_ts = self._now_ts()
        today = datetime.fromtimestamp(now_ts, zone_for(params.timezone)).date()
        self._forget_times_before(today)

        events = self._events_of_today_and_tomorrow(today, params.timezone)
        next_remaining = self._fire_due_events(events, now_ts, params.timezone)

        self._forget_handled_before(today - timedelta(days=_HANDLED_RETENTION_DAYS))
        return self._sleep_until(next_remaining)

    def _use_current_calculation(self) -> CalculationParams:
        params = self._settings.calculation_params
        if params != self._calc_key:
            self._calc_key = params
            self._times.clear()
        return params

    def _forget_times_before(self, today: date) -> None:
        for day in [day for day in self._times if day < today]:
            del self._times[day]

    def _forget_handled_before(self, horizon: date) -> None:
        self._handled = {key for key in self._handled if key[2].date() >= horizon}

    def _events_of_today_and_tomorrow(self, today: date, tz_name: str) -> list[_Event]:
        today_times = self._times_for(today)
        self._log_day(today, tz_name, today_times)
        events = self._events(today_times)
        # Tomorrow can be impossible to compute near the poles; today's events still matter then.
        with contextlib.suppress(ValueError):
            events += self._events(self._times_for(today + timedelta(days=1)))
        return events

    def _fire_due_events(self, events: list[_Event], now_ts: float, tz_name: str) -> float | None:
        """Fire the events that are due and return the seconds until the next one, if any."""
        grace = self.TAKEOVER_GRACE if self._lock.consume_takeover() else self.GRACE_SECONDS
        next_remaining: float | None = None
        for event in sorted(events, key=lambda event: event.when):
            if event.key in self._handled:
                continue
            delta = now_ts - wall_to_timestamp(event.when, tz_name)
            if delta >= 0:
                self._handled.add(event.key)
                if delta <= grace:
                    self._fire(event)
            elif next_remaining is None or -delta < next_remaining:
                next_remaining = -delta
        return next_remaining

    def _sleep_until(self, next_remaining: float | None) -> float:
        if next_remaining is None:
            return self.MAX_SLEEP
        if next_remaining <= self.PRECISE_WAKE_WINDOW:
            return next_remaining + self.WAKE_MARGIN
        return min(self.MAX_SLEEP, next_remaining / 2)

    def _compose(self, event: _Event) -> tuple[str, str, str]:
        language = self._settings.language
        is_sunrise = event.prayer is Prayer.SUNRISE
        key = MESSAGE_KEYS[(event.kind, is_sunrise)]
        values = {
            "prayer": tr(event.prayer.label_key_on(event.when.date()), language=language),
            "time": event.when.strftime("%H:%M"),
            "minutes": event.minutes,
        }
        title = tr(f"{key}.title", language=language, **values)
        body = tr(f"{key}.body", language=language, **values)
        icon = PRAYER_ICONS.get(event.prayer, DEFAULT_ICON) if event.kind is EventKind.PRAYER else DEFAULT_ICON
        return title, body, icon

    def _fire(self, event: _Event) -> None:
        title, body, icon = self._compose(event)

        def send() -> None:
            try:
                logger.info("Notification: %s", title)
                self._notify(title, body, icon)
            except Exception as error:  # noqa: BLE001 - one failed notification must not affect the next
                logger.error("Failed to send the notification: %r", error)

        if self._threaded:
            threading.Thread(target=send, daemon=True).start()
        else:
            send()
