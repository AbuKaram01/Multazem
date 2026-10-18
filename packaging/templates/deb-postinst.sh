#!/bin/sh
# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT
set -e
# Upgrading from the former name (salah-reminder): a copy of the old application that is
# still running would keep sending its own notifications next to the new one. The pattern
# is anchored on the old interpreter command line so nothing unrelated can match. The
# user's settings and background service are migrated by the application on first start.
pkill -f -- '^[^ ]*python[0-9.]* (-m salah_reminder|[^ ]*/salah-reminder)( |$)' >/dev/null 2>&1 || true
# Makes the app icon show up immediately instead of only after the next
# unrelated package triggers a cache rebuild (or a logout/login).
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
