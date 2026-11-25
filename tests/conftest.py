# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Shared pytest fixtures: per-test environment isolation, fake clock, recording notifier and scheduler factory."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Falls back to the copy bundled with the project when pytest runs without the dependencies installed.
try:
    import adhanpy  # noqa: F401
except ImportError:  # pragma: no cover
    sys.path.append(str(ROOT / "packaging" / "vendor"))


# On Windows the GTK runtime has to be made findable before PyGObject is imported (this does nothing elsewhere).
from multazem import winsupport  # noqa: E402

winsupport.prepare_runtime()

try:
    import gi  # noqa: F401
except ImportError:  # pragma: no cover
    # These modules import GLib at module level, so without PyGObject they cannot even be collected. The tests
    # that need the toolkit are skipped and everything else (the core, the settings, the Windows code) still runs.
    collect_ignore = ["test_hijri.py", "test_i18n.py", "test_location.py", "test_scheduler_processes.py"]


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Points HOME and the configuration and data directories (XDG and Windows) at the test's temporary directory.

    Applied to every test so that nothing can read or write the developer's real configuration or runtime
    directory (lock files, sockets). Environment changes are undone by ``monkeypatch`` after the test.

    Returns:
        The test's ``tmp_path``, which now contains an empty ``run`` directory.
    """
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "config"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "data"))
    (tmp_path / "run").mkdir()
    return tmp_path


@pytest.fixture(autouse=True, scope="session")
def console_logging():
    """Installs the application's console log handler once per test session.

    The handler looks up ``sys.stdout`` and ``sys.stderr`` on every record, so ``capsys`` in individual tests
    still sees the output. Without it the ``multazem`` loggers would have no handler at all, because they do
    not propagate to the root logger.
    """
    from multazem.logs import configure_logging

    configure_logging()


@pytest.fixture(autouse=True)
def default_language():
    """Resets the process-wide UI language to the default before and after every test.

    The active language is global state, so a test that switches it must not leak into the next one.
    """
    from multazem.i18n import DEFAULT_LANGUAGE, set_language

    set_language(DEFAULT_LANGUAGE)
    yield
    set_language(DEFAULT_LANGUAGE)


@pytest.fixture
def off_windows(monkeypatch):
    """Makes the path functions behave as on Linux, whatever system the tests run on.

    For the tests of the XDG rules: on real Windows the configuration lives in ``%APPDATA%`` instead.
    """
    from multazem.services import paths

    monkeypatch.setattr(paths, "is_windows", lambda: False)


@pytest.fixture
def settings_path(tmp_path):
    """The location of a ``settings.json`` that does not exist yet, inside the test's temporary directory."""
    return tmp_path / "cfg" / "settings.json"


@pytest.fixture
def settings(settings_path):
    """A ``Settings`` store with default values backed by ``settings_path``."""
    from multazem.services.settings import Settings

    return Settings(settings_path)


@pytest.fixture
def regions_path(tmp_path):
    """The location of a ``regions.json`` that does not exist yet, inside the test's temporary directory."""
    return tmp_path / "cfg" / "regions.json"


@pytest.fixture
def catalog(regions_path):
    """A ``RegionCatalog`` with no custom regions, persisting to ``regions_path``."""
    from multazem.services.region_catalog import RegionCatalog

    return RegionCatalog(regions_path)


class FakeClock:
    """A controllable replacement for ``time.time``, expressed as Unix timestamps in seconds.

    Instances are callable, so they can be passed wherever the scheduler expects its ``now_ts`` function. Time
    only moves when a test calls ``set_wall`` or ``advance``, which keeps the scheduler tests deterministic.

    Attributes:
        ts: The current time as a Unix timestamp in seconds.
    """

    def __init__(self, ts: float = 0.0):
        self.ts = ts

    def __call__(self) -> float:
        """Returns the current fake timestamp, like ``time.time()``."""
        return self.ts

    def set_wall(self, tz_name: str, y, mo, d, h=0, mi=0, s=0):
        """Moves the clock to a wall-clock time in the given time zone.

        Args:
            tz_name: IANA time-zone name, for example ``"Africa/Cairo"``.
            y: Year.
            mo: Month.
            d: Day of the month.
            h: Hour.
            mi: Minute.
            s: Second; may be fractional, for example ``59.5``.

        Returns:
            The new Unix timestamp.
        """
        from multazem.core.timeutil import wall_to_timestamp

        whole = int(s)
        self.ts = wall_to_timestamp(datetime(y, mo, d, h, mi, whole), tz_name) + (s - whole)
        return self.ts

    def advance(self, seconds: float):
        """Moves the clock forward by ``seconds``."""
        self.ts += seconds


@pytest.fixture
def clock():
    """A fresh ``FakeClock`` starting at timestamp 0."""
    return FakeClock()


class RecordingNotifier:
    """Stands in for ``send_notification`` and records each call instead of showing a desktop notification.

    Args:
        clock: The fake clock whose time is stamped on each call; when omitted the stamp is ``None``.

    Attributes:
        calls: One ``(timestamp, title, body, icon)`` tuple per notification, in the order they were sent.
        clock: The fake clock given to the constructor, if any.
    """

    def __init__(self, clock=None):
        self.calls, self.clock = [], clock

    def __call__(self, title, body, icon):
        """Records one notification, stamped with the fake clock's time when there is one."""
        self.calls.append((self.clock.ts if self.clock else None, title, body, icon))

    @property
    def titles(self):
        """The titles of the recorded notifications, in the order they were sent."""
        return [call[1] for call in self.calls]


@pytest.fixture
def make(settings_path, clock, tmp_path):
    """A factory that builds a ``NotificationScheduler`` driven by the fake clock and a recording notifier.

    Each scheduler gets its own ``Settings`` object by default, but all share the same settings file, so a test
    can change settings from "another process" by creating a second ``Settings(settings_path)``. Schedulers are
    stopped when the test ends, which releases their lock files.

    Call it as ``make(settings=None, lock="lock", **kwargs)``. A different ``lock`` name gives a second scheduler
    its own lock file; the remaining keyword arguments are passed to ``NotificationScheduler``.

    Returns:
        A function that returns ``(scheduler, recorder)``, where ``recorder`` is the scheduler's ``RecordingNotifier``.
    """
    pytest.importorskip("gi", reason="the scheduler needs PyGObject (GLib)")
    from multazem.services.scheduler import NotificationScheduler
    from multazem.services.settings import Settings

    schedulers = []

    def _make(settings=None, lock="lock", **kwargs):
        recorder = RecordingNotifier(clock)
        scheduler = NotificationScheduler(
            settings or Settings(settings_path),
            notify=recorder,
            now_ts=clock,
            lock_path=tmp_path / lock,
            **kwargs,
        )
        schedulers.append(scheduler)
        return scheduler, recorder

    yield _make
    for scheduler in schedulers:
        scheduler.stop()
