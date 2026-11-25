# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Markers for the few tests that need something that only some systems offer."""

import time

import pytest

# A program can change the time zone of its own process only where ``time.tzset`` exists (not on Windows).
needs_tzset = pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="a program cannot change the machine's time zone on Windows"
)
