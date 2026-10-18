# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

from enum import Enum


class CalculationMethod(Enum):
    EGYPTIAN = "egyptian"
    MUSLIM_WORLD_LEAGUE = "muslim_world_league"
    NORTH_AMERICA = "north_america"
    UMM_AL_QURA = "umm_al_qura"
    KARACHI = "karachi"
    KUWAIT = "kuwait"
    QATAR = "qatar"

    @property
    def label_key(self) -> str:
        return f"method.{self.value}"


ASR_SHADOW_STANDARD = 1
ASR_SHADOW_HANAFI = 2
VALID_ASR_SHADOWS = (ASR_SHADOW_STANDARD, ASR_SHADOW_HANAFI)
