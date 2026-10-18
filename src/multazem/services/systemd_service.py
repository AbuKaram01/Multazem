# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..i18n import tr
from ..logs import get_logger
from .paths import absolute_directory_from_environment, config_home

logger = get_logger("migration")

SERVICE_NAME = "multazem.service"
LEGACY_SERVICE_NAME = "salah-reminder.service"
_SERVICE_DIR = config_home() / "systemd" / "user"
_SERVICE_PATH = _SERVICE_DIR / SERVICE_NAME


def _quote(argument: str) -> str:
    escaped = argument.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    return f'"{escaped}"'


def _exec_args() -> tuple[list[str], dict[str, str]]:
    installed = shutil.which("multazem")
    if installed:
        return [installed, "--headless"], {}
    package_parent = str(Path(__file__).resolve().parent.parent.parent)
    paths = [package_parent]
    existing = os.environ.get("PYTHONPATH", "")
    if existing:
        paths.append(existing)
    return (
        [sys.executable, "-m", "multazem", "--headless"],
        {"PYTHONPATH": os.pathsep.join(paths)},
    )


def _service_environment(extra: dict[str, str]) -> dict[str, str]:
    uid = os.getuid()
    environment = {
        "XDG_RUNTIME_DIR": f"/run/user/{uid}",
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
        **extra,
    }
    config_override = absolute_directory_from_environment("XDG_CONFIG_HOME")
    if config_override is not None:
        environment["XDG_CONFIG_HOME"] = str(config_override)
    return environment


def _service_content() -> str:
    args, extra_environment = _exec_args()
    environment = _service_environment(extra_environment)
    env_lines = "\n".join(f"Environment={_quote(f'{name}={value}')}" for name, value in environment.items())
    exec_line = " ".join(_quote(argument) for argument in args)
    return f"""[Unit]
Description=Multazem - prayer time notifications
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Type=simple
ExecStart={exec_line}
Restart=on-failure
RestartSec=10
{env_lines}

[Install]
WantedBy=graphical-session.target
"""


def _run_systemctl(*args: str, timeout: float = 10) -> tuple[bool, str]:
    """Run ``systemctl --user`` and return ``(succeeded, combined output or error)``."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return False, "systemctl was not found on this system"
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)


def _unit_is_enabled(unit: str) -> bool:
    ok, output = _run_systemctl("is-enabled", unit, timeout=5)
    return ok and "enabled" in output


def _first_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[0] if lines else ""


def service_is_enabled() -> bool:
    return _unit_is_enabled(SERVICE_NAME)


def service_is_active() -> bool:
    ok, output = _run_systemctl("is-active", SERVICE_NAME, timeout=5)
    return ok and _first_line(output) == "active"


def service_install() -> tuple[bool, str]:
    try:
        _SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        _SERVICE_PATH.write_text(_service_content(), encoding="utf-8")
    except OSError as error:
        return False, tr("service.error.write_failed", detail=error)

    _run_systemctl("daemon-reload")
    ok, output = _run_systemctl("enable", "--now", SERVICE_NAME)
    if not ok:
        with contextlib.suppress(OSError):
            _SERVICE_PATH.unlink(missing_ok=True)
            _run_systemctl("daemon-reload")
        return False, tr("service.error.enable_failed", detail=output)
    return True, tr("service.installed")


def service_uninstall() -> tuple[bool, str]:
    _run_systemctl("disable", "--now", SERVICE_NAME)
    try:
        _SERVICE_PATH.unlink(missing_ok=True)
    except OSError as error:
        return False, tr("service.error.remove_failed", detail=error)
    _run_systemctl("daemon-reload")
    return True, tr("service.uninstalled")


def migrate_legacy_service() -> bool:
    legacy_path = _SERVICE_DIR / LEGACY_SERVICE_NAME
    if not legacy_path.exists():
        return False
    was_enabled = _unit_is_enabled(LEGACY_SERVICE_NAME)
    _run_systemctl("disable", "--now", LEGACY_SERVICE_NAME)
    try:
        legacy_path.unlink(missing_ok=True)
    except OSError as error:
        logger.warning("Could not remove %s: %s", legacy_path, error)
        return False
    _run_systemctl("daemon-reload")
    logger.info("Removed the old %s unit", LEGACY_SERVICE_NAME)
    if was_enabled and not service_is_enabled():
        _installed, message = service_install()
        logger.info("Background service: %s", message)
    return True
