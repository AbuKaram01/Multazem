# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Every source file carries the short SPDX header, not the full license text, matching the declared licenses."""

from __future__ import annotations

import os
import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
HOLDER = "2026 AbuKaram01 <abukaram01@proton.me>"
SKIPPED_DIRS = {
    "vendor",
    "work",
    "pkg",
    "dist",
    "build",
    "node_modules",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
}
# Folders that the installation scripts and the installer build fill with other people's files.
GENERATED_DIRS = {"packaging/gtk", "packaging/python", "packaging/wheelhouse"}
SUFFIXES = {".py", ".sh", ".toml", ".desktop", ".xml", ".svg"}
OWN_LICENSE = {"com.github.multazem.metainfo.xml": "CC0-1.0"}
HEADER_WINDOW_LINES = 6


def _is_foreign_directory(folder: Path) -> bool:
    """Returns whether ``folder`` holds files that are not the project's: a virtual environment or generated output.

    A virtual environment is recognised by its ``pyvenv.cfg``, whatever it is called: the CI jobs and the installation
    scripts create one inside the checkout, and its thousands of library files carry other people's licenses.
    """
    relative = folder.relative_to(ROOT).as_posix()
    return (
        folder.name in SKIPPED_DIRS
        or folder.name.endswith(".egg-info")
        or relative in GENERATED_DIRS
        or (folder / "pyvenv.cfg").is_file()
    )


def _source_files() -> list[Path]:
    """Returns the project's source files that must carry a license header."""
    files = []
    for folder, subfolders, names in os.walk(ROOT):
        subfolders[:] = [name for name in subfolders if not _is_foreign_directory(Path(folder, name))]
        files.extend(Path(folder, name) for name in names if Path(name).suffix in SUFFIXES or name == "PKGBUILD")
    return sorted(files)


SOURCE_FILES = _source_files()


def _id(path: Path) -> str:
    """Returns the path relative to the project root, used as the test id."""
    return str(path.relative_to(ROOT))


def test_the_sources_are_found():
    names = {p.name for p in SOURCE_FILES}
    assert {"app.py", "PKGBUILD", "pyproject.toml", "build.sh", "com.github.multazem.svg"} <= names
    assert len(SOURCE_FILES) > 60


@pytest.mark.parametrize("path", SOURCE_FILES, ids=_id)
def test_file_has_the_short_spdx_header(path: Path):
    head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:HEADER_WINDOW_LINES])
    license_id = OWN_LICENSE.get(path.name, "MIT")
    assert f"SPDX-FileCopyrightText: {HOLDER}" in head
    assert f"SPDX-License-Identifier: {license_id}" in head


@pytest.mark.parametrize("path", SOURCE_FILES, ids=_id)
def test_file_does_not_repeat_the_license_text(path: Path):
    boilerplate = "Permission is hereby " + "granted"
    assert boilerplate not in path.read_text(encoding="utf-8")


def test_the_headers_agree_with_the_declared_licenses():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"]["text"] == "MIT"
    metainfo = ET.parse(ROOT / "data" / "com.github.multazem.metainfo.xml").getroot()
    assert metainfo.findtext("metadata_license") == OWN_LICENSE["com.github.multazem.metainfo.xml"]
    assert metainfo.findtext("project_license") == "MIT"
    assert f"Copyright (c) {HOLDER.split(' <')[0]}" in (ROOT / "LICENSE").read_text(encoding="utf-8")
