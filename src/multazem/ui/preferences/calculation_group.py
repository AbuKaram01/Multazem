# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Calculation method and Asr school."""

from __future__ import annotations

from gi.repository import Adw, Gtk

from ...core.calculation import (
    ASR_SHADOW_HANAFI,
    ASR_SHADOW_STANDARD,
    CalculationMethod,
)
from ...i18n import tr
from ...services.settings import Settings
from .compare_dialog import show_method_comparison

_ASR_OPTIONS = (ASR_SHADOW_STANDARD, ASR_SHADOW_HANAFI)


class CalculationGroup(Adw.PreferencesGroup):
    """Preferences group for the calculation method, the method comparison and the Asr school.

    Args:
        settings: The settings to read and write.
        dialog_parent: The window the comparison dialog is shown over.
    """

    def __init__(self, settings: Settings, dialog_parent: Gtk.Window) -> None:
        super().__init__(title=tr("prefs.calculation.title"))
        self._settings = settings
        self._dialog_parent = dialog_parent
        self._methods = list(CalculationMethod)

        self.add(self._build_method_row())
        self.add(self._build_compare_row())
        self.add(self._build_asr_row())

    def _build_method_row(self) -> Adw.ComboRow:
        """Builds the calculation-method selector."""
        row = Adw.ComboRow(title=tr("prefs.calculation.method"), subtitle=tr("prefs.calculation.method.subtitle"))
        row.set_model(Gtk.StringList.new([tr(method.label_key) for method in self._methods]))
        row.set_selected(self._methods.index(self._settings.calculation_method))
        row.connect("notify::selected", self._on_method_selected)
        return row

    def _on_method_selected(self, row: Adw.ComboRow, _pspec: object) -> None:
        """Stores the chosen calculation method."""
        self._settings.calculation_method = self._methods[row.get_selected()]

    def _build_compare_row(self) -> Adw.ActionRow:
        """Builds the row that opens the method comparison."""
        row = Adw.ActionRow(title=tr("prefs.compare.title"), subtitle=tr("prefs.compare.subtitle"))
        row.set_activatable(True)
        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
        row.connect(
            "activated",
            lambda _row: show_method_comparison(self._dialog_parent, self._settings),
        )
        return row

    def _build_asr_row(self) -> Adw.ComboRow:
        """Builds the Asr school selector."""
        row = Adw.ComboRow(title=tr("prefs.asr.title"))
        row.set_model(Gtk.StringList.new([tr("prefs.asr.standard"), tr("prefs.asr.hanafi")]))
        row.set_selected(_ASR_OPTIONS.index(self._settings.asr_shadow))
        row.connect("notify::selected", self._on_asr_selected)
        return row

    def _on_asr_selected(self, row: Adw.ComboRow, _pspec: object) -> None:
        """Stores the chosen Asr shadow length."""
        self._settings.asr_shadow = _ASR_OPTIONS[row.get_selected()]
