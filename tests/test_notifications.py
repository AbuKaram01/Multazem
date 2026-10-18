# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Desktop notifications through a fake ``notify-send``: arguments, Arabic text and failure reporting."""

import os
import stat
import subprocess
import sys
import threading
import time

import pytest

from multazem.core.prayers import Prayer
from multazem.services import notifications as notif
from multazem.services.notifications import PRAYER_ICONS, send_notification

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="notify-send is for Linux; see test_windows_toast.py")


def fake_notify_send(tmp_path, monkeypatch, script: str):
    """Puts an executable ``notify-send`` running the shell ``script`` first on ``PATH``; returns its path."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    exe = bindir / "notify-send"
    exe.write_text("#!/bin/sh\n" + script)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    return exe


def test_success_passes_title_body_and_icon_unmangled(tmp_path, monkeypatch):
    out = tmp_path / "args"
    fake_notify_send(tmp_path, monkeypatch, f'printf "%s\\n" "$@" > "{out}"\n')
    assert send_notification("Dhuhr prayer time", "It is 12:42", "weather-clear-symbolic") == (True, "")
    args = out.read_text(encoding="utf-8").splitlines()
    assert args[-2:] == ["Dhuhr prayer time", "It is 12:42"] and "weather-clear-symbolic" in args


def test_arabic_text_passes_through_unmangled(tmp_path, monkeypatch):
    out = tmp_path / "args"
    fake_notify_send(tmp_path, monkeypatch, f'printf "%s\\n" "$@" > "{out}"\n')
    assert send_notification("حان وقت الظهر", "الساعة 12:42") == (True, "")
    assert out.read_text(encoding="utf-8").splitlines()[-2:] == ["حان وقت الظهر", "الساعة 12:42"]


def test_app_name_is_the_same_brand_in_both_languages(tmp_path, monkeypatch):
    from multazem.i18n import set_language

    out = tmp_path / "args"
    fake_notify_send(tmp_path, monkeypatch, f'printf "%s\\n" "$@" > "{out}"\n')
    send_notification("t", "b")
    assert "Multazem" in out.read_text(encoding="utf-8")
    set_language("ar")
    send_notification("t", "b")
    assert "Multazem" in out.read_text(encoding="utf-8")


def test_failure_returns_the_reason(tmp_path, monkeypatch):
    fake_notify_send(tmp_path, monkeypatch, 'echo "Cannot autolaunch D-Bus without X11 \\$DISPLAY" >&2\nexit 1\n')
    ok, message = send_notification("t", "b")
    assert not ok and "D-Bus" in message


def test_hanging_notify_send_times_out_instead_of_blocking(tmp_path, monkeypatch):
    fake_notify_send(tmp_path, monkeypatch, "sleep 30\n")
    real_run = subprocess.run
    monkeypatch.setattr(notif.subprocess, "run", lambda *a, **k: real_run(*a, **{**k, "timeout": 0.5}))
    started = time.time()
    ok, message = send_notification("t", "b")
    assert not ok and "5" in message and time.time() - started < 5


def test_missing_binary_is_reported(monkeypatch):
    monkeypatch.setattr(notif.shutil, "which", lambda name: None)
    ok, message = send_notification("t", "b")
    assert not ok and "libnotify" in message


def test_every_timetable_entry_has_an_icon():
    assert set(Prayer) <= set(PRAYER_ICONS)


def test_threaded_engine_does_not_block_the_caller(settings, clock, tmp_path):
    pytest.importorskip("gi", reason="the scheduler needs PyGObject (GLib)")
    from multazem.services.scheduler import NotificationScheduler

    release, started, main = threading.Event(), threading.Event(), threading.get_ident()
    seen = {}

    def slow(title, body, icon):
        seen["thread"] = threading.get_ident()
        started.set()
        release.wait(5)

    engine = NotificationScheduler(settings, notify=slow, now_ts=clock, lock_path=tmp_path / "lock", threaded=True)
    clock.set_wall("Africa/Cairo", 2026, 10, 9, 12, 42, 1)
    began = time.time()
    engine.tick()
    assert time.time() - began < 1
    assert started.wait(2) and seen["thread"] != main
    release.set()
    engine.stop()
