# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Side-effecting services: files, processes, D-Bus, systemd and the network.

Modules here may depend on :mod:`multazem.core` and :mod:`multazem.i18n` but
never on the GTK UI, so the background service can run without importing any widgets.
"""
