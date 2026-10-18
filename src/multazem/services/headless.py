# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Background mode (``--headless``): one long-lived process that sends notifications.

On Linux the process is supervised by ``systemd --user`` (see ``systemd_service``), which is only
responsible for *starting* it and restarting it after a crash; on Windows the autostart entry
starts it (see ``windows_service``). The timing precision lives in the shared scheduler
(``scheduler.py``), the same engine the GUI uses, so there is no duplicated logic and no
behavioural difference between the two modes.
"""

from __future__ import annotations

import signal
from typing import Any

from gi.repository import GLib

from ..i18n import set_language
from ..logs import get_logger
from .background_service import register_background_process
from .legacy_config import migrate_legacy_config
from .scheduler import NotificationScheduler
from .settings import Settings

logger = get_logger("headless")


class HeadlessScheduler(NotificationScheduler):
    """The shared scheduler plus its own GLib main loop (the GUI uses GTK's loop)."""

    def __init__(self, settings: Settings, **kwargs: Any) -> None:
        super().__init__(settings, **kwargs)
        self._loop = GLib.MainLoop()
        self._stop_requested = False

    def run(self) -> None:
        """Starts the scheduler and blocks in the main loop until :meth:`stop` is called.

        Returns immediately when a stop was requested before the loop started.
        """
        if self._stop_requested:
            return
        self.start()
        self._loop.run()

    def stop(self) -> None:
        """Stops the scheduler and ends the main loop; safe to call before :meth:`run`."""
        self._stop_requested = True
        super().stop()
        self._loop.quit()


def run_headless() -> None:
    """Runs the notification scheduler without a window until SIGTERM or SIGINT arrives.

    Migrates the configuration of the former application name, loads the settings and follows later
    language changes made by the GUI. Returns at once when another background process is already running
    (only detectable on Windows).
    """
    with register_background_process() as claimed:
        if claimed:
            _run_scheduler()
        else:
            logger.info("multazem: a background process is already running")


def _run_scheduler() -> None:
    """Runs the scheduler of :func:`run_headless` until it is asked to stop."""
    migrate_legacy_config()
    settings = Settings()
    set_language(settings.language)
    # Follow language changes made in the GUI while this service keeps running.
    settings.add_listener(lambda _key: set_language(settings.language))
    scheduler = HeadlessScheduler(settings)

    def request_stop(*_args: object) -> None:
        scheduler.stop()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    logger.info("multazem: running with precise scheduling in a single process ✓")
    scheduler.run()
    logger.info("multazem: stopped")
