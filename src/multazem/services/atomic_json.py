# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Crash-safe JSON file writing shared by the settings and the custom-regions store."""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .paths import is_windows

# Windows refuses to replace a file while another program (the window and the background process read the same file)
# has it open, and the reader is gone a moment later: the replacement is tried again for about half a second.
REPLACE_ATTEMPTS = 50
REPLACE_PAUSE_SECONDS = 0.01


def _move_into_place(temporary: Path, path: Path) -> None:
    """Moves ``temporary`` over ``path``; on Windows it tries again while a reader has ``path`` open.

    Raises:
        PermissionError: if the file stays locked (Windows) or may not be replaced (elsewhere, at once).
    """
    attempts = REPLACE_ATTEMPTS if is_windows() else 1
    for attempt in range(1, attempts + 1):
        try:
            temporary.replace(path)
        except PermissionError:
            if attempt == attempts:
                raise
            time.sleep(REPLACE_PAUSE_SECONDS)
        else:
            return


def write_json_atomic(path: Path, payload: Any) -> None:
    """Writes ``payload`` as UTF-8 JSON so readers never observe a partial file.

    The data goes to a temporary file next to the target and is moved into place with
    :func:`os.replace`, which is atomic on POSIX (and on Windows, where it is retried while a reader has the file
    open). The GUI and the background service are
    separate processes that read the same file; plain ``write_text`` truncates first and
    writes afterwards, so a reader arriving in between used to see an empty or partial
    file and treat it as corrupt.

    Args:
        path: The file to write; its directory is created when missing.
        payload: Any JSON-serialisable value.

    Raises:
        OSError: if the directory cannot be created or the file cannot be written. No
            temporary file is left behind in that case and the original is untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp")
    temporary = Path(temporary_name)
    replaced = False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _move_into_place(temporary, path)
        replaced = True
    finally:
        if not replaced:
            with contextlib.suppress(OSError):
                temporary.unlink()


def backup_corrupt_file(path: Path) -> None:
    """Moves an unreadable data file aside as ``<name>.corrupt`` so it is not lost.

    The user (or a developer) can still inspect the damaged content after the application
    has started over with fresh data. Failing to back it up is not worth crashing for.
    """
    with contextlib.suppress(OSError):
        path.replace(path.with_name(path.name + ".corrupt"))
