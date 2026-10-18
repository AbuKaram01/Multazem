# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The systemd user service: unit file content, quoting, install and uninstall, with a fake ``systemctl``."""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from multazem.services import systemd_service as svc

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="systemd exists only on Linux")


def unit_for(monkeypatch, which_result):
    """Returns the unit file text as generated when ``shutil.which`` finds ``which_result`` for ``multazem``."""
    monkeypatch.setattr(shutil, "which", lambda name: which_result)
    return svc._service_content()


def line(unit, prefix):
    """Returns the lines of a unit file that start with ``prefix``."""
    return [ln for ln in unit.splitlines() if ln.startswith(prefix)]


def test_restart_policy_recovers_from_python_crash(monkeypatch):
    unit = unit_for(monkeypatch, "/usr/bin/multazem")
    assert "Restart=on-failure" in unit and "on-abnormal" not in unit


def test_paths_with_spaces_and_systemd_specials_are_quoted(monkeypatch):
    unit = unit_for(monkeypatch, "/home/u/My Projects/50%/$HOME/.venv/bin/multazem")
    assert line(unit, "ExecStart=") == ['ExecStart="/home/u/My Projects/50%%/$$HOME/.venv/bin/multazem" "--headless"']


def test_installed_launcher_needs_no_pythonpath(monkeypatch):
    unit = unit_for(monkeypatch, "/usr/bin/multazem")
    assert "PYTHONPATH" not in unit


def test_source_run_gets_a_pythonpath(monkeypatch):
    monkeypatch.delenv("PYTHONPATH", raising=False)
    unit = unit_for(monkeypatch, None)
    assert f'"{sys.executable}" "-m" "multazem" "--headless"' in line(unit, "ExecStart=")[0]
    src = str(Path(svc.__file__).resolve().parent.parent.parent)
    assert f'Environment="PYTHONPATH={src}"' in unit


def test_custom_xdg_config_home_is_forwarded_to_the_service(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "my cfg"))
    assert f'Environment="XDG_CONFIG_HOME={tmp_path / "my cfg"}"' in unit_for(monkeypatch, "/usr/bin/multazem")
    monkeypatch.setenv("XDG_CONFIG_HOME", "")
    assert "XDG_CONFIG_HOME" not in unit_for(monkeypatch, "/usr/bin/multazem")


def test_unit_dir_follows_xdg_config_home(tmp_path):
    out = subprocess.run(
        [sys.executable, "-c", "import multazem.services.systemd_service as s; print(s._SERVICE_DIR)"],
        capture_output=True,
        text=True,
        env={**os.environ, "XDG_CONFIG_HOME": str(tmp_path / "c"), "PYTHONPATH": ":".join(sys.path)},
        check=False,
    )
    assert out.stdout.strip() == str(tmp_path / "c" / "systemd" / "user")


def _verify(path: Path) -> str:
    """Runs ``systemd-analyze verify`` on a unit file and returns its output."""
    r = subprocess.run(
        ["systemd-analyze", "--man=no", "verify", str(path)], capture_output=True, text=True, check=False
    )
    return r.stdout + r.stderr


@pytest.mark.skipif(not shutil.which("systemd-analyze"), reason="systemd-analyze is not available")
def test_generated_unit_passes_systemd_analyze_verify(monkeypatch, tmp_path):
    exe = tmp_path / "My Dir" / "multazem"
    exe.parent.mkdir()
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)

    old = tmp_path / "old.service"
    old.write_text(f"[Service]\nExecStart={exe} --headless\n")
    if "not executable" not in _verify(old):
        pytest.skip("systemd-analyze verify does not detect the bad syntax in this environment")

    unit_file = tmp_path / "multazem.service"
    unit_file.write_text(unit_for(monkeypatch, str(exe)), encoding="utf-8")
    out = _verify(unit_file)
    bad = [
        ln
        for ln in out.splitlines()
        if any(k in ln for k in ("not executable", "Invalid", "Unknown key", "Failed to parse", "Unbalanced"))
    ]
    assert bad == [], out


def fake_systemctl(monkeypatch, results):
    """Replaces ``systemctl`` by a recorder that answers from ``results`` (success by default); returns its calls."""
    calls = []

    def run(*args, timeout=10):
        calls.append(args)
        return results.get(args[0], (True, ""))

    monkeypatch.setattr(svc, "_run_systemctl", run)
    return calls


@pytest.mark.parametrize(
    "out,ok,expected",
    [
        ("active\n", True, True),
        ("inactive\n", False, False),
        ("failed\n", False, False),
        ("activating\n", True, False),
        ("", False, False),
    ],
)
def test_service_is_active_parsing(monkeypatch, out, ok, expected):
    fake_systemctl(monkeypatch, {"is-active": (ok, out)})
    assert svc.service_is_active() is expected


def test_install_writes_unit_and_enables_it(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "_SERVICE_DIR", tmp_path / "d")
    monkeypatch.setattr(svc, "_SERVICE_PATH", tmp_path / "d" / "multazem.service")
    calls = fake_systemctl(monkeypatch, {})
    ok, _ = svc.service_install()
    assert ok and (tmp_path / "d" / "multazem.service").exists()
    assert ("enable", "--now", "multazem.service") in calls


def test_failed_enable_leaves_no_orphan_unit(monkeypatch, tmp_path):
    monkeypatch.setattr(svc, "_SERVICE_DIR", tmp_path / "d")
    monkeypatch.setattr(svc, "_SERVICE_PATH", tmp_path / "d" / "multazem.service")
    fake_systemctl(monkeypatch, {"enable": (False, "boom")})
    ok, msg = svc.service_install()
    assert not ok and "boom" in msg and not (tmp_path / "d" / "multazem.service").exists()


def test_install_into_unwritable_dir_reports_instead_of_raising(monkeypatch, tmp_path):
    (tmp_path / "blocker").write_text("x")
    monkeypatch.setattr(svc, "_SERVICE_DIR", tmp_path / "blocker" / "sub")
    monkeypatch.setattr(svc, "_SERVICE_PATH", tmp_path / "blocker" / "sub" / "u.service")
    ok, msg = svc.service_install()
    assert not ok and "Could not write the service file" in msg


def test_uninstall_removes_unit_even_if_disable_fails(monkeypatch, tmp_path):
    unit = tmp_path / "multazem.service"
    unit.write_text("x")
    monkeypatch.setattr(svc, "_SERVICE_PATH", unit)
    fake_systemctl(monkeypatch, {"disable": (False, "not loaded")})
    assert svc.service_uninstall()[0] and not unit.exists()


def test_missing_systemctl_is_reported_not_raised(monkeypatch):
    def nope(*a, **k):
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", nope)
    ok, msg = svc._run_systemctl("is-enabled", "x")
    assert not ok and "systemctl" in msg
    assert svc.service_is_enabled() is False and svc.service_is_active() is False
