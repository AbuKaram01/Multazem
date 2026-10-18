# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from gi.repository import Adw

MAX_TOAST_LENGTH = 110


def make_toast(message: str, timeout_seconds: int = 3) -> Adw.Toast:
    text = " ".join(message.split())
    if len(text) > MAX_TOAST_LENGTH:
        text = text[: MAX_TOAST_LENGTH - 3] + "…"
    toast = Adw.Toast.new(text)
    toast.set_timeout(timeout_seconds)
    return toast
