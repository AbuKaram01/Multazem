# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Notification scheduling engine shared by the GUI and the background (headless) mode.

Design principle: *graduated sleep with the real clock re-read on every wake-up.* Instead
of one timer per notification (``threading.Timer``) there is a single GLib timer that
wakes up, reads the real wall clock, sends whatever is due and computes its next sleep.
This solves several problems of the earlier design:

* **Suspend.** Python/GLib timers use a monotonic clock that stops while the machine
  sleeps, so every long timer was delayed by the sleep duration and its notification
  was dropped as "stale". The longest sleep here is ``MAX_SLEEP`` seconds and each wake-up
  consults the real clock.
* **Machine time zone != configured city.** Events are compared as absolute timestamps
  while the timetable is calculated in the city's time zone.
* **Settings changed by another process** (the GUI edits them while the service runs):
  every wake-up checks the settings file (a single cheap ``stat``).
* **Duplicates between GUI and service.** Only the process holding the lock sends
  notifications; the other waits and takes over automatically when the first exits.
* **Exceptions.** Nothing raised inside a round may kill the scheduling: it is logged and
  retried a minute later.
"""

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
    """What an event announces: the prayer itself or the reminder shown beforehand."""

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
    """One notification that is due at a point in time.

    Attributes:
        when: Wall-clock time at the location at which the event is due.
        kind: Whether it is the prayer or its reminder.
        prayer: The timetable entry it belongs to.
        minutes: For a reminder, how many minutes ahead of the prayer it fires; 0 otherwise.
    """

    when: datetime
    kind: EventKind
    prayer: Prayer
    minutes: int = 0

    @property
    def key(self) -> tuple:
        """Identity used to remember which events were already handled."""
        return (self.kind, self.prayer, self.when)


class NotificationScheduler:
    """Sends the prayer and reminder notifications on time.

    Call :meth:`start` once; from then on a GLib timer runs :meth:`tick` and re-arms itself with the
    delay that :meth:`tick` returns. Only the process that holds the leader lock notifies (see
    :class:`~multazem.services.process_lock.ProcessLock`).

    Args:
        settings: The settings to read on every round.
        notify: ``(title, body, icon)`` callable; injectable for tests.
        now_ts: Clock returning a Unix timestamp; injectable for tests.
        lock_path: Override of the leader-lock file.
        threaded: Send notifications from a worker thread. The GUI uses this so a
            slow ``notify-send`` cannot freeze the interface.
    """

    # An event missed by more than this (machine asleep, app closed) is dropped silently instead of
    # being announced late.
    GRACE_SECONDS = 90
    # Longest sleep between wake-ups. Bounds the delay of a notification after a resume and the delay
    # before a settings change made elsewhere is noticed.
    MAX_SLEEP = 30.0
    # How long a process that is not the leader waits before trying to take the lock again.
    LOCK_RETRY = 5.0
    # How long to wait after invalid settings or an unexpected error. The user may fix the settings
    # from the GUI at any moment.
    ERROR_RETRY = 60.0
    # When this process takes over from another one (the GUI closed and the service continues), any
    # event older than this was already sent by the previous leader.
    TAKEOVER_GRACE = LOCK_RETRY + 1.0
    # Within this many seconds of the next event the scheduler sleeps until the event itself, plus a
    # small margin so the clock has certainly passed it when it wakes up.
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
        """Starts scheduling; the first round runs almost immediately on the GLib main loop."""
        self._running = True
        self._arm(0.0)

    def refresh(self) -> None:
        """Runs a round right away (after the user changed a setting in the GUI).

        Does nothing while the scheduler is stopped.
        """
        if self._running:
            self._arm(0.0)

    def stop(self) -> None:
        """Stops scheduling and releases the leader lock so another process can take over."""
        self._running = False
        self._disarm()
        self._lock.release()

    @property
    def is_leader(self) -> bool:
        """Whether this process holds the leader lock and therefore sends the notifications."""
        return self._lock.held

    def _arm(self, seconds: float) -> None:
        """Schedules the next round ``seconds`` from now, replacing any pending one."""
        self._disarm()
        if self._running:
            self._source = GLib.timeout_add(max(1, int(seconds * 1000)), self._on_timeout)

    def _disarm(self) -> None:
        """Cancels the pending round, if any."""
        if self._source is not None:
            GLib.source_remove(self._source)
            self._source = None

    def _on_timeout(self) -> bool:
        """GLib timer callback: runs a round, then re-arms the timer with the delay it asked for.

        Always returns ``False`` because the timer is re-armed explicitly. Anything raised by a round is
        logged and retried after ``ERROR_RETRY`` seconds.
        """
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
        """Does everything that is due and returns how many seconds to sleep until the next round.

        A round never raises. Without the leader lock nothing is sent and the result is ``LOCK_RETRY``;
        invalid settings or an unexpected error are logged once and retried after ``ERROR_RETRY``.
        """
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
            # Invalid settings (time zone, polar location, ...). Try again in a minute: the user may fix
            # them from the GUI at any moment.
            self._log_once(logging.WARNING, f"Invalid settings: {error}")
            return self.ERROR_RETRY
        except Exception as error:  # noqa: BLE001 - report it, then try again in a minute
            self._log_once(logging.ERROR, f"Error: {error!r}")
            return self.ERROR_RETRY

    def _log_once(self, level: int, message: str) -> None:
        """Logs a message only when it differs from the previous one (no log spam)."""
        if message != self._last_error:
            self._last_error = message
            logger.log(level, "%s", message)

    def _log_day(self, today: date, tz_name: str, times: PrayerTimes) -> None:
        """Logs one line per day with the timetable in force.

        It shows up in the service log (``journalctl --user -u multazem``) so the
        user can verify the times are renewed every day; changing the city or the method
        logs the line again with the new values.
        """
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
        """Returns the timetable of ``day`` for the current calculation settings, computing it once."""
        assert self._calc_key is not None
        if day not in self._times:
            self._times[day] = self._calc_key.prayer_times(day)
        return self._times[day]

    def _events(self, times: PrayerTimes) -> list[_Event]:
        """Returns the events of one timetable: prayer and reminder per enabled entry, as the settings ask."""
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
        """Runs one round and returns the seconds to sleep.

        Drops cached data that is no longer needed, fires what is due and computes the next wake-up.
        """
        params = self._use_current_calculation()
        now_ts = self._now_ts()
        today = datetime.fromtimestamp(now_ts, zone_for(params.timezone)).date()
        self._forget_times_before(today)

        events = self._events_of_today_and_tomorrow(today, params.timezone)
        next_remaining = self._fire_due_events(events, now_ts, params.timezone)

        self._forget_handled_before(today - timedelta(days=_HANDLED_RETENTION_DAYS))
        return self._sleep_until(next_remaining)

    def _use_current_calculation(self) -> CalculationParams:
        """Returns the current calculation settings, discarding cached timetables when they changed."""
        params = self._settings.calculation_params
        if params != self._calc_key:
            self._calc_key = params
            self._times.clear()
        return params

    def _forget_times_before(self, today: date) -> None:
        """Drops the cached timetables of days before ``today``."""
        for day in [day for day in self._times if day < today]:
            del self._times[day]

    def _forget_handled_before(self, horizon: date) -> None:
        """Forgets the handled events of days before ``horizon``, which can no longer come due."""
        self._handled = {key for key in self._handled if key[2].date() >= horizon}

    def _events_of_today_and_tomorrow(self, today: date, tz_name: str) -> list[_Event]:
        """Returns the events of today and, when it can be calculated, of tomorrow."""
        today_times = self._times_for(today)
        self._log_day(today, tz_name, today_times)
        events = self._events(today_times)
        # Tomorrow's Fajr reminder can fall before midnight (early Fajr plus a long reminder, or high
        # latitudes), so tomorrow has to be inspected as well. It can be impossible to compute near the
        # poles; today's events still matter then.
        with contextlib.suppress(ValueError):
            events += self._events(self._times_for(today + timedelta(days=1)))
        return events

    def _fire_due_events(self, events: list[_Event], now_ts: float, tz_name: str) -> float | None:
        """Fires the events that are due and returns the seconds until the next one, if any.

        An event is marked handled as soon as it is due. It is sent only if it is not older than the grace
        period; a longer-overdue one (machine asleep, app closed) is dropped silently.
        """
        grace = self.TAKEOVER_GRACE if self._lock.consume_takeover() else self.GRACE_SECONDS
        next_remaining: float | None = None
        for event in sorted(events, key=lambda event: event.when):
            if event.key in self._handled:
                continue
            delta = now_ts - wall_to_timestamp(event.when, tz_name)
            if delta >= 0:
                # Marked as handled *before* sending: if sending fails we must not retry the same event in
                # a tight loop.
                self._handled.add(event.key)
                if delta <= grace:
                    self._fire(event)
            elif next_remaining is None or -delta < next_remaining:
                next_remaining = -delta
        return next_remaining

    def _sleep_until(self, next_remaining: float | None) -> float:
        """Returns how long to sleep when the next event is ``next_remaining`` seconds away.

        With no known event (``None``) it sleeps ``MAX_SLEEP``. Otherwise, far away, it sleeps half the
        remaining time but never more than ``MAX_SLEEP``, so the real clock is re-read often; within the
        last second it sleeps until the event itself plus a small margin.
        """
        if next_remaining is None:
            return self.MAX_SLEEP
        if next_remaining <= self.PRECISE_WAKE_WINDOW:
            return next_remaining + self.WAKE_MARGIN
        return min(self.MAX_SLEEP, next_remaining / 2)

    def _compose(self, event: _Event) -> tuple[str, str, str]:
        """Returns the ``(title, body, icon)`` of the notification, in the configured language.

        The name is resolved for the event's own date, so the Friday prayer is announced
        as such. Sunrise is not a prayer and has its own wording ("the sun is rising",
        not "time for Sunrise prayer").
        """
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
        """Sends the notification of ``event``, on a worker thread when the scheduler is threaded.

        A failure to send is logged and never raised.
        """
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
