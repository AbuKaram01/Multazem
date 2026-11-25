# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Small helpers that connect preference rows to settings attributes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gi.repository import Adw

from ..services.settings import Settings


def bind_switch_row(row: Adw.SwitchRow, settings: Settings, attribute: str) -> None:
    """Initialises ``row`` from ``settings.<attribute>`` and writes changes back to it.

    Args:
        row: The switch row to bind.
        settings: The settings object that owns the attribute.
        attribute: Name of a boolean property of ``settings``.
    """
    row.set_active(getattr(settings, attribute))
    row.connect("notify::active", lambda r, _pspec: setattr(settings, attribute, r.get_active()))


def bind_spin_row(
    row: Adw.SpinRow,
    settings: Settings,
    attribute: str,
    convert: Callable[[float], Any] = float,
) -> None:
    """Initialises a spin row from ``settings.<attribute>`` and writes changes back.

    Args:
        row: The spin row to bind.
        settings: The settings object that owns the attribute.
        attribute: Name of a numeric property of ``settings``.
        convert: Converts the row's float value to the type the setting stores.
    """
    row.set_value(getattr(settings, attribute))
    row.connect("changed", lambda r: setattr(settings, attribute, convert(r.get_value())))
