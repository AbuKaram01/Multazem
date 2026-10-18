# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from collections.abc import Callable
from typing import Any

from gi.repository import Adw

from ..services.settings import Settings


def bind_switch_row(row: Adw.SwitchRow, settings: Settings, attribute: str) -> None:
    row.set_active(getattr(settings, attribute))
    row.connect("notify::active", lambda r, _pspec: setattr(settings, attribute, r.get_active()))


def bind_spin_row(
    row: Adw.SpinRow,
    settings: Settings,
    attribute: str,
    convert: Callable[[float], Any] = float,
) -> None:
    row.set_value(getattr(settings, attribute))
    row.connect("changed", lambda r: setattr(settings, attribute, convert(r.get_value())))
