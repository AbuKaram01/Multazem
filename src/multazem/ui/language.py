# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Applying the selected language to the toolkit (text direction)."""

from __future__ import annotations

from gi.repository import Gtk

from ..i18n import is_rtl, set_language


def apply_ui_language(language: str) -> None:
    """Switches the process-wide language and mirrors the UI for right-to-left languages.

    Must be called after GTK is initialised. Widgets created afterwards (and existing
    widgets without an explicit direction) follow the new default direction.
    """
    set_language(language)
    direction = Gtk.TextDirection.RTL if is_rtl() else Gtk.TextDirection.LTR
    Gtk.Widget.set_default_direction(direction)
