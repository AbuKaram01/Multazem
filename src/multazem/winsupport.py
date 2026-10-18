# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Windows-only start-up work: locating the GTK runtime, console-less launches, taskbar identity and icon.

Every public function does nothing on other systems, and nothing here imports GTK, so the module can be imported
(and tested) anywhere. :func:`prepare_runtime` must run before ``import gi``; :mod:`multazem.app` calls it first.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

from .services.paths import is_windows, local_data_dir, log_file, windows_icon_file
from .services.windows_toast import APP_USER_MODEL_ID

GTK_DIR_ENV = "MULTAZEM_GTK_DIR"
# A log that has grown past this size is moved aside when the program starts, so it cannot fill the disk.
MAX_LOG_BYTES = 1024 * 1024

# --- The GTK runtime ---


def gtk_candidates() -> list[Path]:
    """Returns the folders that may hold a Windows GTK 4 runtime as built by gvsbuild, best guess first."""
    candidates: list[Path] = []
    explicit = os.environ.get(GTK_DIR_ENV)
    if explicit:
        candidates.append(Path(explicit))
    candidates += [
        # The Windows installer puts the runtime next to the Python environment: <install>\.venv and <install>\gtk.
        Path(sys.prefix).parent / "gtk",
        # Where scripts/install-windows.ps1 puts it.
        local_data_dir() / "gtk",
        # The documented location of the prebuilt gvsbuild archive, and gvsbuild's own build output.
        Path("C:/gtk"),
        Path("C:/gtk-build/gtk/x64/release"),
    ]
    return candidates


def is_gtk_runtime(folder: Path) -> bool:
    """Returns whether ``folder`` looks like a GTK 4 runtime: a ``bin`` folder and the GObject typelibs."""
    return (folder / "bin").is_dir() and (folder / "lib" / "girepository-1.0").is_dir()


def find_gtk_runtime() -> Path | None:
    """Returns the first of :func:`gtk_candidates` that is a GTK runtime, or ``None`` when there is none."""
    return next((folder for folder in gtk_candidates() if is_gtk_runtime(folder)), None)


def _prepend(variable: str, value: str) -> None:
    """Puts ``value`` at the front of the path-list environment variable ``variable``, unless it is in it."""
    current = os.environ.get(variable)
    parts = current.split(os.pathsep) if current else []
    if value not in parts:
        os.environ[variable] = os.pathsep.join([value, *parts])


def configure_gtk(gtk: Path) -> None:
    """Makes the DLLs, typelibs, schemas and icons of the runtime in ``gtk`` visible to this process.

    Since Python 3.8 Windows no longer searches ``PATH`` for the DLLs of extension modules, so the ``bin``
    folder is registered with ``os.add_dll_directory`` as well as put on ``PATH`` (child processes and GLib's own
    module loading still use ``PATH``).
    """
    binaries = gtk / "bin"
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        add_dll_directory(str(binaries))
    _prepend("PATH", str(binaries))
    _prepend("GI_TYPELIB_PATH", str(gtk / "lib" / "girepository-1.0"))
    if (gtk / "share").is_dir():
        _prepend("XDG_DATA_DIRS", str(gtk / "share"))
    schemas = gtk / "share" / "glib-2.0" / "schemas"
    if (schemas / "gschemas.compiled").is_file():
        os.environ.setdefault("GSETTINGS_SCHEMA_DIR", str(schemas))


# --- Process set-up ---


def ensure_standard_streams() -> None:
    """Gives a console-less process (``pythonw.exe``) working ``stdout`` and ``stderr``.

    Without them the first log line raises. Both go to the log file, so what the background process reports can
    still be read afterwards; if the file cannot be opened the output is discarded.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = None
    try:
        path = log_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            path.replace(path.with_suffix(".old"))
        stream = path.open("a", encoding="utf-8", buffering=1)
    except OSError:
        stream = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115 - kept open for the process
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def set_app_user_model_id() -> None:
    """Gives the process its own taskbar identity instead of the one it shares with every Python program."""
    with contextlib.suppress(Exception):
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)  # type: ignore[attr-defined]


def prepare_runtime() -> None:
    """Does everything that must happen before GTK is imported; nothing off Windows. Safe to call twice."""
    if not is_windows():
        return
    ensure_standard_streams()
    gtk = find_gtk_runtime()
    if gtk is not None:
        configure_gtk(gtk)
    set_app_user_model_id()


def report_missing_toolkit(error: BaseException) -> None:
    """Tells the user that GTK could not be loaded; a launch without a console has nowhere else to say it."""
    if not is_windows():
        return
    text = (
        "Multazem could not load GTK 4 and libadwaita.\n\n"
        f"{error}\n\n"
        "Run scripts\\install-windows.ps1 to install them, or set the "
        f"{GTK_DIR_ENV} environment variable to a GTK 4 runtime folder (see the Windows section of the README)."
    )
    if sys.stderr is not None:
        sys.stderr.write(text + "\n")
    with contextlib.suppress(Exception):
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "Multazem", 0x10)  # type: ignore[attr-defined]


# --- Icon ---


def apply_icon_to_own_windows() -> None:
    """Sets the title-bar and taskbar icon of this process's visible top-level windows, as far as it can.

    GTK 4 has no icon API on Windows, so the window would show the icon of Python. Failure is silent: the
    application works the same without the icon.
    """
    if not is_windows():
        return
    icon = windows_icon_file()
    if icon is None:
        return
    with contextlib.suppress(Exception):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        # Win32 constants: IMAGE_ICON, LR_LOADFROMFILE and WM_SETICON.
        image_icon, load_from_file, wm_seticon = 1, 0x10, 0x80
        # GetSystemMetrics indices 11/12 and 49/50 are SM_CXICON/SM_CYICON and SM_CXSMICON/SM_CYSMICON: the sizes
        # the shell uses for the large (taskbar, Alt+Tab) and the small (title bar) icon.
        big = user32.LoadImageW(
            None, str(icon), image_icon, user32.GetSystemMetrics(11), user32.GetSystemMetrics(12), load_from_file
        )
        small = user32.LoadImageW(
            None, str(icon), image_icon, user32.GetSystemMetrics(49), user32.GetSystemMetrics(50), load_from_file
        )
        own_pid = os.getpid()

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _lparam):
            """Sets the icons of one window if it is a visible window of this process."""
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == own_pid and user32.IsWindowVisible(hwnd):
                # WM_SETICON's wParam selects the slot: 1 = ICON_BIG, 0 = ICON_SMALL.
                if big:
                    user32.SendMessageW(hwnd, wm_seticon, 1, big)
                if small:
                    user32.SendMessageW(hwnd, wm_seticon, 0, small)
            return True

        user32.EnumWindows(visit, 0)
