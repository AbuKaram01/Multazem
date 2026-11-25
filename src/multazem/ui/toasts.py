# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Helpers for in-app toast notifications."""

from __future__ import annotations

from gi.repository import Adw

MAX_TOAST_LENGTH = 110


def make_toast(message: str, timeout_seconds: int = 3) -> Adw.Toast:
    """Builds a toast from ``message``.

    ``Adw.Toast`` is a single-line bar of limited width, so a long or multi-line message
    (raw ``systemctl`` output after a failure, for example) gets cut off or looks broken.
    Whitespace and line breaks are folded into one line and the text is truncated as a
    last resort. Having this one choke point means callers need not care about the
    length of their messages.

    Args:
        message: The text to show.
        timeout_seconds: How long the toast stays on screen.
    """
    text = " ".join(message.split())
    if len(text) > MAX_TOAST_LENGTH:
        text = text[: MAX_TOAST_LENGTH - 3] + "…"
    toast = Adw.Toast.new(text)
    toast.set_timeout(timeout_seconds)
    return toast
