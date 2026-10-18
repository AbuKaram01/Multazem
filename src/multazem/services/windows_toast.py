# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Windows toast notifications, raised through Windows PowerShell.

GLib has no notification backend on Windows, so a toast is shown by a short PowerShell program. Windows PowerShell
5.1 ships with Windows 10 and 11 and projects the WinRT toast API, which means no extra Python package is needed.
The program is handed over as an encoded command, so the title and the text never have to be quoted for a shell.

Windows only shows a toast for a program it knows, so the application registers its own identity (a name and an
icon) for the current user before the first one. Nothing here needs administrator rights.
"""

from __future__ import annotations

import base64
import subprocess
from xml.sax.saxutils import escape

from ..i18n import tr
from .paths import windows_icon_file

APP_USER_MODEL_ID = "com.github.multazem"
# Starting Windows PowerShell takes a second or two on a slow machine.
TOAST_TIMEOUT_SECONDS = 30
_REGISTRY_KEY = rf"Software\Classes\AppUserModelId\{APP_USER_MODEL_ID}"
_CREATE_NO_WINDOW = 0x08000000


def toast_script(title: str, body: str, app_id: str = APP_USER_MODEL_ID) -> str:
    """Returns the PowerShell program that shows one toast.

    The text is escaped for XML and then quoted for PowerShell. A failure is written to standard error as plain
    text and ends the program with exit code 1, so the caller can report the reason.

    Args:
        title: First line of the toast.
        body: Second line of the toast.
        app_id: The application identity the toast is shown for.
    """

    def quote(text: str) -> str:
        return "'" + text.replace("'", "''") + "'"

    xml = (
        '<toast><visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(body)}</text>"
        "</binding></visual></toast>"
    )
    manager = "Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications"
    xml_document = "Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument"
    return "\n".join(
        [
            "$ErrorActionPreference = 'Stop'",
            "try {",
            f"    [{manager}, ContentType = WindowsRuntime] | Out-Null",
            f"    [{xml_document}, ContentType = WindowsRuntime] | Out-Null",
            "    $document = New-Object Windows.Data.Xml.Dom.XmlDocument",
            f"    $document.LoadXml({quote(xml)})",
            "    $toast = [Windows.UI.Notifications.ToastNotification]::new($document)",
            f"    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier({quote(app_id)})"
            ".Show($toast)",
            "} catch {",
            "    [Console]::Error.WriteLine($_.Exception.Message)",
            "    exit 1",
            "}",
        ]
    )


def powershell_command(script: str) -> list[str]:
    """Returns the ``powershell.exe`` command line that runs ``script``.

    The script is passed as base64 of its UTF-16 little-endian bytes, the encoding that ``-EncodedCommand``
    expects, which keeps quotes and Arabic text intact.
    """
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return [
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-WindowStyle",
        "Hidden",
        "-ExecutionPolicy",
        "Bypass",
        "-EncodedCommand",
        encoded,
    ]


def register_toast_app() -> None:
    """Registers the application's identity (name and icon) for the current user so that its toasts are shown.

    Raises:
        OSError: When the registry cannot be written.
    """
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REGISTRY_KEY) as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, tr("app.name"))
        icon = windows_icon_file()
        if icon is not None:
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(icon))


def send_toast(title: str, body: str) -> tuple[bool, str]:
    """Shows a toast and waits for PowerShell to finish.

    Returns:
        ``(True, "")`` on success, otherwise ``(False, reason)``. The reason is a technical diagnostic and
        stays in English.
    """
    try:
        register_toast_app()
    except OSError as error:
        return False, f"the notification identity could not be registered: {error}"

    try:
        result = subprocess.run(
            powershell_command(toast_script(title, body)),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=TOAST_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW),
            check=False,
        )
    except FileNotFoundError:
        return False, "powershell.exe was not found"
    except subprocess.TimeoutExpired:
        return False, f"powershell.exe did not finish within {TOAST_TIMEOUT_SECONDS} seconds"
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)

    if result.returncode != 0:
        return False, result.stderr.strip() or f"powershell.exe exited with code {result.returncode}"
    return True, ""
