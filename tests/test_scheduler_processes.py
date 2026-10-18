# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Several scheduler processes: a single leader, failover, hand-over without gaps and GLib timer handling."""

import os
import pathlib
import sys
import tempfile

import pytest

from multazem.services import process_lock
from multazem.services import scheduler as sched

from scheduler_support import (
    ASR,
    CAIRO,
    DHUHR,
    D,
)


def test_only_one_process_notifies(make, clock):
    gui, rec_gui = make(lock="shared", threaded=False)
    svc, rec_svc = make(lock="shared")
    clock.set_wall(CAIRO, *D, 12, 41, 59)
    assert gui.tick() <= 1.02 and gui.is_leader
    assert svc.tick() == svc.LOCK_RETRY and not svc.is_leader
    clock.advance(1.02)
    gui.tick()
    svc.tick()
    assert rec_gui.titles == [DHUHR] and rec_svc.calls == []


def test_failover_takes_over_without_duplicating_or_missing(make, clock):
    a, rec_a = make(lock="shared")
    b, rec_b = make(lock="shared")
    clock.set_wall(CAIRO, *D, 12, 41, 0)
    a.tick()
    b.tick()
    clock.set_wall(CAIRO, *D, 12, 42, 0.1)
    a.tick()
    assert rec_a.titles == [DHUHR]
    clock.set_wall(CAIRO, *D, 12, 42, 30)
    a.stop()
    assert b.tick() > 0 and b.is_leader
    assert rec_b.calls == []
    clock.set_wall(CAIRO, *D, 15, 59, 59)
    clock.advance(b.tick())
    b.tick()
    assert rec_b.titles == [ASR]


def test_failover_still_delivers_an_event_that_came_due_during_the_handover_gap(make, clock):
    a, _ = make(lock="shared")
    b, rec_b = make(lock="shared")
    clock.set_wall(CAIRO, *D, 12, 41, 50)
    a.tick()
    b.tick()
    a.stop()
    clock.set_wall(CAIRO, *D, 12, 42, 3)
    b.tick()
    assert rec_b.titles == [DHUHR]


class FakeGLib:
    """Replaces the ``GLib`` module of the scheduler and records the timers it arms and removes."""

    def __init__(self):
        self.added, self.removed, self.n = [], [], 0

    def timeout_add(self, ms, cb):
        self.n += 1
        self.added.append((self.n, ms, cb))
        return self.n

    def source_remove(self, sid):
        self.removed.append(sid)


def test_glib_arming_survives_exceptions_and_stops_cleanly(make, monkeypatch):
    fake = FakeGLib()
    monkeypatch.setattr(sched, "GLib", fake)
    eng, _ = make()
    eng.start()
    assert fake.added[-1][1] == 1
    monkeypatch.setattr(eng, "tick", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert eng._on_timeout() is False
    assert fake.added[-1][1] == int(eng.ERROR_RETRY * 1000)
    sid = fake.added[-1][0]
    eng.stop()
    assert sid in fake.removed
    n = len(fake.added)
    eng.refresh()
    assert len(fake.added) == n
    assert eng._on_timeout() is False and len(fake.added) == n


def test_lock_released_on_stop_and_reacquirable(make, clock):
    a, _ = make(lock="L")
    b, _ = make(lock="L")
    clock.set_wall(CAIRO, *D, 9, 0, 0)
    a.tick()
    assert b.tick() == b.LOCK_RETRY
    a.stop()
    assert not a.is_leader
    b.tick()
    assert b.is_leader


@pytest.mark.skipif(sys.platform == "win32", reason="the runtime directory is a Linux concept")
def test_default_lock_path_prefers_runtime_dir(monkeypatch, tmp_path):
    run = tmp_path / "xdg"
    run.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(run))
    assert process_lock.default_lock_path() == run / "multazem.lock"
    monkeypatch.setenv("XDG_RUNTIME_DIR", "relative")
    monkeypatch.setattr(os, "getuid", lambda: 987654)
    assert process_lock.default_lock_path() == pathlib.Path(tempfile.gettempdir()) / "multazem-987654.lock"
