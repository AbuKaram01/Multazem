# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Dialog that compares Fajr and Isha across all calculation methods."""

from __future__ import annotations

from dataclasses import replace

from gi.repository import Adw, Gtk

from ...core.calculation import CalculationMethod
from ...core.prayer_times import CalculationParams
from ...i18n import describe_error, tr
from ...services.settings import Settings

_COLUMN_WIDTHS = (240, 65, 65)
_ROW_MARGIN = 3
_SEPARATOR_MARGIN = 6
_TABLE_MARGIN = 12


def _cell(text: str, width: int, *, caption: bool = False, accent: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_size_request(width, -1)
    label.set_halign(Gtk.Align.START)
    if caption:
        label.add_css_class("caption")
        label.add_css_class("dim-label")
    else:
        label.add_css_class("numeric")
    if accent:
        label.add_css_class("accent")
    return label


def _row(texts: tuple[str, str, str], *, header: bool = False, current: bool = False) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    if not header:
        row.set_margin_top(_ROW_MARGIN)
        row.set_margin_bottom(_ROW_MARGIN)
    for text, width in zip(texts, _COLUMN_WIDTHS, strict=True):
        row.append(_cell(text, width, caption=header, accent=current))
    return row


def _separator() -> Gtk.Separator:
    separator = Gtk.Separator()
    separator.set_margin_top(_SEPARATOR_MARGIN)
    separator.set_margin_bottom(_SEPARATOR_MARGIN)
    return separator


def _error_label(error: ValueError) -> Gtk.Label:
    label = Gtk.Label(label=f"⚠️ {describe_error(error)}")
    label.set_wrap(True)
    return label


def _build_table(params: CalculationParams) -> Gtk.Box:
    table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    table.set_margin_top(_TABLE_MARGIN)
    table.append(
        _row(
            (tr("prefs.compare.column.method"), tr("prefs.compare.column.fajr"), tr("prefs.compare.column.isha")),
            header=True,
        )
    )
    table.append(_separator())

    try:
        timetables = [(method, replace(params, method=method).prayer_times()) for method in CalculationMethod]
    except ValueError as error:
        table.append(_error_label(error))
        return table

    for method, times in timetables:
        texts = (tr(method.label_key), times.fajr.strftime("%H:%M"), times.isha.strftime("%H:%M"))
        table.append(_row(texts, current=method == params.method))
    return table


def show_method_comparison(parent: Gtk.Window, settings: Settings) -> None:
    dialog = Adw.AlertDialog()
    dialog.set_heading(tr("prefs.compare.dialog.heading"))
    dialog.set_body(tr("prefs.compare.dialog.body"))
    dialog.add_response("close", tr("prefs.compare.dialog.close"))
    dialog.set_default_response("close")
    dialog.set_extra_child(_build_table(settings.calculation_params))
    dialog.present(parent)
