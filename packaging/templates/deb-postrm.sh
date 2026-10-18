#!/bin/sh
# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT
set -e
# Safety net for anything written under /opt/multazem at runtime that
# dpkg never tracked (shouldn't happen with PYTHONDONTWRITEBYTECODE set,
# but this guarantees a clean removal either way).
if [ "$1" = "purge" ] || [ "$1" = "remove" ]; then
    rm -rf /opt/multazem
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
