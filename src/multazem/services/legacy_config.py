# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT


from __future__ import annotations

import shutil

from ..logs import get_logger
from .paths import config_dir, legacy_config_dir

logger = get_logger("migration")

MIGRATED_FILES = ("settings.json", "regions.json")


def migrate_legacy_config() -> list[str]:
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
