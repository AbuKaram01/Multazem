# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""One-time migration of the user's files from the application's former name.

The application used to be called ``salah-reminder`` and was renamed to Multazem. Its
settings and the regions the user added live in a directory named after the application,
so without this step a user who upgrades would find every choice reset.

The files are *copied*, never moved: the old directory stays untouched as a backup, and
running the migration again never overwrites anything the new version already wrote.
"""

from __future__ import annotations

import shutil

from ..logs import get_logger
from .paths import config_dir, legacy_config_dir

logger = get_logger("migration")

# The files worth carrying over: the settings and the user's own regions.
MIGRATED_FILES = ("settings.json", "regions.json")


def migrate_legacy_config() -> list[str]:
    """Copies the former configuration files that the new directory does not have yet.

    Returns:
        The names of the files that were copied (empty when there was nothing to do). A failure is
        logged as a warning and never raised: starting without the old settings is better than
        not starting.
    """
    old_dir = legacy_config_dir()
    new_dir = config_dir()
    copied: list[str] = []
    for name in MIGRATED_FILES:
        source, target = old_dir / name, new_dir / name
        if target.exists() or not source.is_file():
            continue
        staging = target.with_name(target.name + ".migrating")
        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staging)
            staging.replace(target)
        except OSError as error:
            logger.warning("Could not copy %s to %s: %s", source, target, error)
            staging.unlink(missing_ok=True)
            continue
        copied.append(name)
    if copied:
        logger.info("Copied %s from %s", ", ".join(copied), old_dir)
    return copied
