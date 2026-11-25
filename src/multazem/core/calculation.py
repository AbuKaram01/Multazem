# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Vocabulary of the prayer-time calculation: methods and the Asr juristic school."""

from __future__ import annotations

from enum import Enum


class CalculationMethod(Enum):
    """Supported calculation authorities.

    The enum *name* is what gets persisted in the settings file, so renaming a member is
    a breaking change for existing users. The value is used to build the translation key.
    """

    EGYPTIAN = "egyptian"
    MUSLIM_WORLD_LEAGUE = "muslim_world_league"
    NORTH_AMERICA = "north_america"
    UMM_AL_QURA = "umm_al_qura"
    KARACHI = "karachi"
    KUWAIT = "kuwait"
    QATAR = "qatar"

    @property
    def label_key(self) -> str:
        """Translation key of the display name (see :mod:`multazem.i18n`)."""
        return f"method.{self.value}"


# Shadow length that decides when Asr starts, as a multiple of the object's height: 1x for the
# Shafi'i, Maliki and Hanbali schools, 2x for the Hanafi school.
ASR_SHADOW_STANDARD = 1
ASR_SHADOW_HANAFI = 2
VALID_ASR_SHADOWS = (ASR_SHADOW_STANDARD, ASR_SHADOW_HANAFI)
