# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The GTK runtime of the Windows installer, with the PowerShell scripts run for real.

Covers turning a downloaded zip into a runtime folder, leaving out what only builds need, checking the zip against its
pinned hash, and choosing which runtime the install script uses.
"""

import hashlib
import subprocess
import zipfile
from pathlib import Path

import pytest

from packaging_support import needs_pwsh, run_gtk_script

GTK_FILES = [
    "bin/gtk-4-1.dll",
    "bin/adwaita-1-0.dll",
    "lib/girepository-1.0/Gtk-4.0.typelib",
    "lib/girepository-1.0/Adw-1.typelib",
    "wheels/PyGObject-3.54.0-cp314-cp314-win_amd64.whl",
    "wheels/pycairo-1.28.0-cp314-cp314-win_amd64.whl",
    "share/glib-2.0/schemas/gschemas.compiled",
]

# What a gvsbuild release carries besides the runtime, and what the build leaves out.
DEVELOPMENT_FILES = [
    "bin/gtk-4-1.pdb",
    "lib/gtk-4.0.lib",
    "lib/pkgconfig/gtk4.pc",
    "lib/cmake/gtk4/gtk4-config.cmake",
    "lib/gobject-introspection/giscanner/main.py",
    "lib/gtkmm-4.0/include/gtkmmconfig.h",
    "include/gtk-4.0/gtk/gtk.h",
    "share/gir-1.0/Gtk-4.0.gir",
    "share/doc/gtk4/README",
    "share/bash-completion/completions/gsettings",
    "bin/gtkmm-vc143-4.0-0.dll",
    "bin/sigc-3.0.dll",
    "bin/libprotobuf.dll",
    "bin/protoc.exe",
    "bin/gettextlib-0-22.dll",
    "bin/xgettext.exe",
    "bin/pkgconf.exe",
    "bin/pkgconf-7.dll",
    "bin/sassc.exe",
    "bin/sass.dll",
]

# What looks like a build tool but is part of the runtime.
KEPT_FILES = [
    "bin/gspawn-win64-helper.exe",
    "bin/gspawn-win64-helper-console.exe",
    "bin/glib-compile-schemas.exe",
    "bin/gdk-pixbuf-query-loaders.exe",
    "lib/gdk-pixbuf-2.0/2.10.0/loaders.cache",
    "share/icons/Adwaita/index.theme",
]


def make_gtk_zip(path: Path, prefix: str = "", skip: tuple[str, ...] = (), extra: tuple[str, ...] = ()) -> Path:
    """A stand-in for GTK4_Gvsbuild_<tag>_x64.zip: the files the install script looks for, with nothing real in them."""
    with zipfile.ZipFile(path, "w") as archive:
        for name in GTK_FILES:
            if name not in skip:
                archive.writestr(prefix + name, b"x")
        for name in extra:
            archive.writestr(prefix + name, b"x" * 1024)
    return path


def get_portable_gtk(tmp_path: Path, target: Path, zip_path: Path, sha256: str = "") -> subprocess.CompletedProcess:
    """Runs Get-PortableGtk from *zip_path* into *target*, checked against *sha256* when one is given.

    The script prints ``RESULT=<what the function answered>``.
    """
    pin = f" -Sha256 '{sha256}'" if sha256 else ""
    return run_gtk_script(
        tmp_path, f"$ok = Get-PortableGtk -Target '{target}' -ZipPath '{zip_path}'{pin}\nWrite-Output \"RESULT=$ok\""
    )


@needs_pwsh
@pytest.mark.parametrize("prefix", ["", "GTK4/"], ids=["at the top", "inside one folder"])
def test_a_gtk_zip_becomes_a_complete_runtime_folder(tmp_path, prefix):
    zip_path = make_gtk_zip(tmp_path / "GTK4_Gvsbuild_2026.8.0_x64.zip", prefix)
    target = tmp_path / "out" / "gtk"
    result = get_portable_gtk(tmp_path, target, zip_path)
    assert "RESULT=True" in result.stdout, result.stdout + result.stderr
    for name in GTK_FILES:
        assert (target / name).is_file(), name
    note = (target / "gvsbuild-release.txt").read_text(encoding="utf-8-sig")
    assert "GTK4_Gvsbuild_2026.8.0_x64.zip" in note and "SHA256 of the zip:" in note
    assert not (tmp_path / "out" / "gtk.partial").exists()


@needs_pwsh
def test_what_only_builds_need_is_left_out_of_the_runtime_and_everything_else_stays(tmp_path):
    """Leaves the installer with 150 MB instead of 1.2 GB.

    Only libraries that the Visual C++ runtime would have to serve (the C++ bindings of GTK) go; the C libraries,
    GLib's helper programs and the icon theme stay.
    """
    zip_path = make_gtk_zip(tmp_path / "gtk.zip", extra=tuple(DEVELOPMENT_FILES + KEPT_FILES))
    target = tmp_path / "out" / "gtk"
    result = get_portable_gtk(tmp_path, target, zip_path)
    assert "RESULT=True" in result.stdout, result.stdout + result.stderr
    assert "Left out what only building against GTK needs" in result.stdout
    for name in DEVELOPMENT_FILES:
        assert not (target / name).exists(), f"{name} should have been left out"
    for name in GTK_FILES + KEPT_FILES:
        assert (target / name).is_file(), f"{name} should have been kept"
    for folder in ("include", "lib/cmake", "lib/pkgconfig", "share/gir-1.0"):
        assert not (target / folder).exists(), folder
    note = (target / "gvsbuild-release.txt").read_text(encoding="utf-8-sig")
    assert "Left out:" in note


@needs_pwsh
def test_the_runtime_is_checked_again_after_the_development_files_are_gone(tmp_path):
    """Test-GtkRuntime has to still be satisfied: nothing the application loads may be on the list of what goes."""
    zip_path = make_gtk_zip(tmp_path / "gtk.zip", extra=tuple(DEVELOPMENT_FILES))
    target = tmp_path / "gtk"
    get_portable_gtk(tmp_path, target, zip_path)
    result = run_gtk_script(tmp_path, f"Write-Output \"COMPLETE=$(Test-GtkRuntime '{target}')\"")
    assert "COMPLETE=True" in result.stdout, result.stdout + result.stderr


@needs_pwsh
def test_an_incomplete_gtk_zip_is_refused_and_leaves_nothing_behind(tmp_path):
    zip_path = make_gtk_zip(tmp_path / "gtk.zip", skip=("lib/girepository-1.0/Adw-1.typelib",))
    target = tmp_path / "out" / "gtk"
    result = get_portable_gtk(tmp_path, target, zip_path)
    assert "RESULT=False" in result.stdout, result.stdout + result.stderr
    assert "not a complete GTK 4" in result.stdout
    assert not target.exists() and not (tmp_path / "out" / "gtk.partial").exists()


@needs_pwsh
def test_a_gtk_zip_must_match_the_hash_it_is_pinned_to(tmp_path):
    zip_path = make_gtk_zip(tmp_path / "gtk.zip")
    right = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    wrong = ("0" if right[0] != "0" else "1") + right[1:]
    bad = get_portable_gtk(tmp_path, tmp_path / "bad", zip_path, sha256=wrong)
    assert "RESULT=False" in bad.stdout and "does not match the expected SHA256" in bad.stdout, bad.stdout + bad.stderr
    assert not (tmp_path / "bad").exists()
    good = get_portable_gtk(tmp_path, tmp_path / "good", zip_path, sha256=right.upper())
    assert "RESULT=True" in good.stdout, good.stdout + good.stderr
    assert right.upper() in (tmp_path / "good" / "gvsbuild-release.txt").read_text(encoding="utf-8-sig").upper()


@needs_pwsh
def test_a_complete_runtime_that_is_already_there_is_left_alone(tmp_path):
    target = tmp_path / "gtk"
    for name in GTK_FILES:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(b"mine")
    result = get_portable_gtk(tmp_path, target, tmp_path / "does-not-exist.zip")
    assert "RESULT=True" in result.stdout, result.stdout + result.stderr
    assert (target / GTK_FILES[0]).read_bytes() == b"mine"


def make_runtime_folder(folder: Path, complete: bool = True) -> Path:
    """A runtime folder with the files that Test-GtkRuntime looks for (all of them, or all but libadwaita's)."""
    for name in GTK_FILES:
        if complete or "Adw-1" not in name:
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(b"x")
    return folder


@needs_pwsh
@pytest.mark.parametrize(
    ("explicit", "bundled", "expected_dir", "custom", "is_bundled"),
    [
        ("mine", "complete", "mine", True, False),  # -GtkDir wins, even over a bundled runtime.
        ("default", "complete", "default", False, False),  # ... and naming the default folder is not "custom".
        (None, "complete", "app/gtk", False, True),  # The runtime inside the installer, found by itself.
        # A damaged one is not used: the default folder (a download).
        (None, "incomplete", "default", False, False),
        (None, None, "default", False, False),  # A checkout has none.
    ],
    ids=["explicit", "explicit default", "bundled", "damaged bundle", "none"],
)
def test_which_gtk_runtime_the_install_script_uses(tmp_path, explicit, bundled, expected_dir, custom, is_bundled):
    folders = {"mine": make_runtime_folder(tmp_path / "mine"), "default": tmp_path / "default"}
    folders["default"].mkdir()
    app = tmp_path / "app"
    app.mkdir()
    if bundled:
        make_runtime_folder(app / "gtk", complete=bundled == "complete")
    explicit_path = str(folders[explicit]) if explicit else ""
    body = (
        f"$c = Resolve-GtkChoice -Explicit '{explicit_path}' -ProjectRoot '{app}' -DefaultDir '{folders['default']}'\n"
        'Write-Output "DIR=$($c.Dir)"\nWrite-Output "CUSTOM=$($c.Custom)"\nWrite-Output "BUNDLED=$($c.Bundled)"'
    )
    result = run_gtk_script(tmp_path, body)
    lines = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(lines["DIR"]) == (tmp_path / expected_dir if expected_dir != "app/gtk" else app / "gtk")
    assert lines["CUSTOM"] == str(custom)
    assert lines["BUNDLED"] == str(is_bundled)


@needs_pwsh
@pytest.mark.parametrize("given, expected", [("", "2026.8.0"), ("2026.10.0", "2026.10.0"), ("2026.6.0", "2026.6.0")])
def test_the_gtk_release_is_the_tested_one_unless_another_is_named(tmp_path, given, expected):
    result = run_gtk_script(tmp_path, f"Write-Output \"TAG=$(Resolve-GtkTag '{given}')\"")
    assert f"TAG={expected}" in result.stdout, result.stdout + result.stderr
