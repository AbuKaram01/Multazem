# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from gi.repository import Gtk

from ..i18n import is_rtl, set_language


def apply_ui_language(language: str) -> None:
    set_language(language)
    direction = Gtk.TextDirection.RTL if is_rtl() else Gtk.TextDirection.LTR
    Gtk.Widget.set_default_direction(direction)
