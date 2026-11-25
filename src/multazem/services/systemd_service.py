# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Installs and removes the ``systemd --user`` service that runs the background mode.

Design note: the service runs *one long-lived process* (``multazem --headless``) and
leaves the timing precision to the shared scheduler. Scheduling each prayer as a separate
``systemd-run`` timer was deliberately avoided: the default ``AccuracySec`` of systemd
timers is a full minute (see ``systemd.timer(5)``), which is far too coarse.
"""

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
# Unit installed by the versions that were still called "salah-reminder".
LEGACY_SERVICE_NAME = "salah-reminder.service"
# systemd looks for user units in $XDG_CONFIG_HOME/systemd/user. The path used to be hard-wired to ~/.config,
# so with a custom XDG_CONFIG_HOME the unit was written where systemd never looked.
_SERVICE_DIR = config_home() / "systemd" / "user"
_SERVICE_PATH = _SERVICE_DIR / SERVICE_NAME


def _quote(argument: str) -> str:
    """Quotes an ``ExecStart``/``Environment`` argument following systemd's rules.

    Backslashes and double quotes are escaped, ``%`` (specifiers) and ``$`` (variable
    expansion) are doubled. Without this a path containing a space (a project folder
    called "My Projects", say) was split into two arguments and the service failed.
    """
    escaped = argument.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$")
    return f'"{escaped}"'


def _exec_args() -> tuple[list[str], dict[str, str]]:
    """Returns ``(command that starts the background mode, extra environment variables)``.

    The installed ``multazem`` entry point is preferred. When running from a source
    checkout (nothing installed) it falls back to ``python -m multazem`` with a
    ``PYTHONPATH``; without it the service started and immediately died with
    ``ModuleNotFoundError``.
    """
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
    """Returns the environment variables the service needs, including ``extra``."""
    uid = os.getuid()
    environment = {
        "XDG_RUNTIME_DIR": f"/run/user/{uid}",
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{uid}/bus",
        **extra,
    }
    # A custom configuration directory must reach the service as well, because ``systemd --user`` does not
    # inherit the session's environment automatically.
    config_override = absolute_directory_from_environment("XDG_CONFIG_HOME")
    if config_override is not None:
        environment["XDG_CONFIG_HOME"] = str(config_override)
    return environment


def _service_content() -> str:
    """Returns the text of the unit file."""
    # Restart=on-failure rather than on-abnormal: the latter restarts only after a signal or timeout. An
    # uncaught Python exception exits with code 1, which systemd counts as a "failure" but not as
    # "abnormal", so the service stayed dead after its first crash.
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
    """Runs ``systemctl --user`` and returns ``(succeeded, combined output or error)``.

    Never raises: a missing ``systemctl``, a timeout or any other failure becomes ``(False, reason)``.
    """
    try:
        result = subprocess.run(
            ["systemctl", "--user", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return False, "systemctl was not found on this system"
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)


def _unit_is_enabled(unit: str) -> bool:
    """Returns whether systemd reports ``unit`` as enabled."""
    ok, output = _run_systemctl("is-enabled", unit, timeout=5)
    return ok and "enabled" in output


def _first_line(text: str) -> str:
    """Returns the first line of ``text`` (empty when there is none)."""
    lines = text.strip().splitlines()
    return lines[0] if lines else ""


def service_is_enabled() -> bool:
    """Returns whether the background service is enabled (starts with the session)."""
    return _unit_is_enabled(SERVICE_NAME)


def service_is_active() -> bool:
    """Returns whether the service is *running* right now.

    "Enabled" does not mean "running": the service may have crashed or been stopped by
    hand. The GUI uses this to decide whether closing itself is safe.
    """
    ok, output = _run_systemctl("is-active", SERVICE_NAME, timeout=5)
    return ok and _first_line(output) == "active"


def service_install() -> tuple[bool, str]:
    """Writes the unit file and enables the service.

    Returns:
        ``(succeeded, message for the user)``. When activation fails the unit file is removed again.
    """
    try:
        _SERVICE_DIR.mkdir(parents=True, exist_ok=True)
        _SERVICE_PATH.write_text(_service_content(), encoding="utf-8")
    except OSError as error:
        return False, tr("service.error.write_failed", detail=error)

    _run_systemctl("daemon-reload")
    ok, output = _run_systemctl("enable", "--now", SERVICE_NAME)
    if not ok:
        # Leaving an orphan unit file behind after a failed activation only causes confusion later (the
        # file exists but was never registered).
        with contextlib.suppress(OSError):
            _SERVICE_PATH.unlink(missing_ok=True)
            _run_systemctl("daemon-reload")
        return False, tr("service.error.enable_failed", detail=output)
    return True, tr("service.installed")


def service_uninstall() -> tuple[bool, str]:
    """Disables the service and deletes its unit file.

    Returns:
        ``(succeeded, message for the user)``.
    """
    _run_systemctl("disable", "--now", SERVICE_NAME)
    try:
        _SERVICE_PATH.unlink(missing_ok=True)
    except OSError as error:
        return False, tr("service.error.remove_failed", detail=error)
    _run_systemctl("daemon-reload")
    return True, tr("service.uninstalled")


def migrate_legacy_service() -> bool:
    """Replaces the unit of the application's former name by the current one.

    The old unit starts a command (``salah-reminder``) that no longer exists, so it would
    fail and restart in a loop forever. It is stopped and removed; when it was enabled, the
    current service is installed in its place so the user keeps their background
    notifications.

    Returns:
        ``True`` when a legacy unit was found and handled.
    """
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
