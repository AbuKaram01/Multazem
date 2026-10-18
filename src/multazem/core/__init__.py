# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Domain logic: prayer calculation, Hijri dates, regions and scheduling rules.

Nothing in this package touches GTK, the file system, the network or D-Bus, so it can be
unit-tested in isolation. It may depend on :mod:`multazem.i18n` only.
"""
