#!/bin/sh
# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT
# Fixed paths — this package always installs to /opt/multazem, which
# also holds the bundled adhanpy library next to the app package. /usr/bin/python3
# is used explicitly (not whatever "python3" comes first in PATH): pyenv, conda
# or a venv would otherwise win and they don't have the system's PyGObject.
# PYTHONDONTWRITEBYTECODE keeps that install-tree read-only at runtime
# (no __pycache__ written under /opt, which the package manager doesn't track
# and would otherwise leave behind — or fail outright — on removal).
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="/opt/multazem${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m multazem "$@"
