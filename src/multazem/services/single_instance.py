# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Keeps the graphical application to one running copy, and lets a second launch wake the first.

On Linux the session bus takes care of this: starting the application again activates the running copy, which
presents its window. Windows has no such bus, and the window may be hidden (closing it leaves the notifications
running), so without help a second launch would open a second copy next to the invisible first one. A named mutex
decides which copy is the first, and a named event carries the "show your window" request to it.

Elsewhere the class does nothing: every launch counts as the first.
"""

from __future__ import annotations

import ctypes
import threading
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

from .paths import is_windows

MUTEX_NAME = "Local\\Multazem.Instance"
EVENT_NAME = "Local\\Multazem.Activate"

_ERROR_ALREADY_EXISTS = 183
_EVENT_MODIFY_STATE = 0x0002
_WAIT_OBJECT_0 = 0
_INFINITE = 0xFFFFFFFF


def _kernel32() -> Any:
    """Returns the ``kernel32`` library with the signatures of the functions used here declared.

    Without declared signatures ctypes passes handles as 32-bit integers, which truncates them in a 64-bit
    process.
    """
    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    library.CreateMutexW.restype = wintypes.HANDLE
    library.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    library.CreateEventW.restype = wintypes.HANDLE
    library.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    library.OpenEventW.restype = wintypes.HANDLE
    library.SetEvent.argtypes = [wintypes.HANDLE]
    library.SetEvent.restype = wintypes.BOOL
    library.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    library.WaitForSingleObject.restype = wintypes.DWORD
    library.CloseHandle.argtypes = [wintypes.HANDLE]
    library.CloseHandle.restype = wintypes.BOOL
    return library


class SingleInstance:
    """Decides whether this process is the first copy of the application and relays activation requests.

    The first copy calls :meth:`acquire` (which succeeds) and then :meth:`listen`; any later copy calls
    :meth:`acquire` (which fails), :meth:`request_activation` and exits. The mutex and the event live as long as
    the first copy does, because Windows removes them when the last handle to them closes.
    """

    def __init__(self) -> None:
        self._mutex = None
        self._event = None

    def acquire(self) -> bool:
        """Claims the right to be the one running copy.

        Returns:
            ``True`` when this is the first copy (always the case off Windows, and when Windows cannot say),
            ``False`` when another copy is already running.
        """
        if not is_windows():
            return True
        library = _kernel32()
        mutex = library.CreateMutexW(None, False, MUTEX_NAME)
        if not mutex:
            return True
        if ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
            library.CloseHandle(mutex)
            return False
        self._mutex = mutex
        # Created at once, so that a copy started right after this one finds the event to signal.
        self._event = library.CreateEventW(None, False, False, EVENT_NAME)
        return True

    def request_activation(self) -> bool:
        """Asks the first copy to present its window.

        Returns:
            ``True`` when the request was delivered.
        """
        if not is_windows():
            return False
        library = _kernel32()
        event = library.OpenEventW(_EVENT_MODIFY_STATE, False, EVENT_NAME)
        if not event:
            return False
        try:
            return bool(library.SetEvent(event))
        finally:
            library.CloseHandle(event)

    def listen(self, callback: Callable[[], None]) -> None:
        """Calls ``callback`` whenever a later copy asks for activation, until the process ends.

        The callback runs on a helper thread, so it must hand the work over to the thread of the interface
        (``GLib.idle_add``) instead of touching widgets itself. Does nothing when there is nothing to listen to.
        """
        event = self._event
        if event is None:
            return
        library = _kernel32()

        def wait() -> None:
            while library.WaitForSingleObject(event, _INFINITE) == _WAIT_OBJECT_0:
                callback()

        threading.Thread(target=wait, name="activation-listener", daemon=True).start()
