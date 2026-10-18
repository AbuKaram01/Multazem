# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The command line: ``--version`` and the headless mode, run as real subprocesses."""

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("gi")

ROOT = Path(__file__).resolve().parent.parent

WINDOWS = sys.platform == "win32"
posix_only = pytest.mark.skipif(WINDOWS, reason="stopping a process with a signal is a POSIX behaviour")


def env_for(tmp_path, **settings):
    """Returns an environment that isolates a subprocess in ``tmp_path`` and writes the given settings file if any."""
    cfg = tmp_path / "cfg"
    if settings:
        (cfg / "multazem").mkdir(parents=True)
        (cfg / "multazem" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    run = tmp_path / "run"
    run.mkdir(exist_ok=True)
    pp = os.pathsep.join([str(ROOT / "src"), str(ROOT / "packaging" / "vendor")])
    return {
        **os.environ,
        "XDG_CONFIG_HOME": str(cfg),
        "XDG_RUNTIME_DIR": str(run),
        # What the same folders are called on Windows.
        "APPDATA": str(cfg),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "TEMP": str(run),
        "TMP": str(run),
        "PYTHONPATH": pp,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
    }


def start_headless(tmp_path, **settings):
    """Starts ``python -m multazem --headless`` with the isolated environment."""
    return subprocess.Popen(
        [sys.executable, "-m", "multazem", "--headless"],
        env=env_for(tmp_path, **settings),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )


def stop(process):
    """Asks the background process to stop and returns its ``(stdout, stderr)``.

    On Windows the signal ends the process at once (there is no way to ask it politely), so a test that
    needs a clean exit is a POSIX test.
    """
    process.send_signal(signal.SIGTERM)
    return process.communicate(timeout=10)


def clean_exit(process):
    """Returns whether the process ended without error; on Windows a stopped process always ends with 1."""
    return WINDOWS or process.returncode == 0


def test_version_flag_prints_and_exits_without_gtk(tmp_path):
    r = subprocess.run(
        [sys.executable, "-m", "multazem", "--version"],
        env=env_for(tmp_path),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    from multazem import __version__

    assert r.returncode == 0 and r.stdout.strip() == f"multazem {__version__}"


@posix_only
def test_headless_starts_and_exits_cleanly_on_sigterm(tmp_path):
    p = start_headless(tmp_path)
    time.sleep(1.5)
    assert p.poll() is None
    t0 = time.time()
    out, err = stop(p)
    assert p.returncode == 0 and time.time() - t0 < 3
    assert "stopped" in out and "Traceback" not in err


def test_headless_survives_a_polar_location_instead_of_crashing(tmp_path):
    p = start_headless(tmp_path, latitude=88.0, longitude=0.0, timezone_name="UTC")
    time.sleep(1.5)
    assert p.poll() is None
    _, err = stop(p)
    assert clean_exit(p) and "Traceback" not in err and "Cannot calculate prayer times" in err


def test_headless_survives_corrupt_settings(tmp_path):
    cfg = tmp_path / "cfg" / "multazem"
    cfg.mkdir(parents=True)
    (cfg / "settings.json").write_text("{not json")
    p = start_headless(tmp_path)
    time.sleep(1.5)
    assert p.poll() is None
    stop(p)
    assert clean_exit(p) and (cfg / "settings.json.corrupt").exists()


@posix_only
def test_second_headless_instance_waits_instead_of_duplicating(tmp_path):
    a = start_headless(tmp_path)
    time.sleep(1.2)
    b = start_headless(tmp_path)
    time.sleep(1.5)
    try:
        lock = tmp_path / "run" / "multazem.lock"
        assert lock.exists()
        assert a.poll() is None and b.poll() is None
    finally:
        for p in (a, b):
            stop(p)


def test_headless_follows_the_language_setting(tmp_path):
    p = start_headless(tmp_path, language="ar")
    time.sleep(1.5)
    assert p.poll() is None
    out, err = stop(p)
    assert clean_exit(p) and "Traceback" not in err and "[scheduler]" in out


@pytest.mark.skipif(not WINDOWS, reason="Windows runs one background process and a second one leaves")
def test_second_background_process_leaves_at_once_on_windows(tmp_path):
    a = start_headless(tmp_path)
    pid_file = tmp_path / "local" / "multazem" / "background.pid"
    try:
        deadline = time.time() + 15
        while not pid_file.exists() and time.time() < deadline:
            time.sleep(0.1)
        assert pid_file.read_text().strip().isdigit()
        b = start_headless(tmp_path)
        _, err = b.communicate(timeout=20)
        assert b.returncode == 0 and "Traceback" not in err
        assert a.poll() is None
    finally:
        # Inside a virtual environment python.exe is a launcher; the process that holds the lock is its child.
        if pid_file.exists():
            with contextlib.suppress(OSError, ValueError):
                os.kill(int(pid_file.read_text()), signal.SIGTERM)
        stop(a)
