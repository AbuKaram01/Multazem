# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""``python -m multazem`` entry point."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
