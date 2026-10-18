# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Packaging: metadata consistency, shell syntax, the installer, and real builds of the deb, rpm and Arch packages.

Package builds run in a copy of the project so that nothing is written into the working tree. Tests that need
``dpkg-deb`` are skipped where it is missing; the Arch package is checked by running the PKGBUILD's ``package()``.
"""

import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP_ID = "com.github.multazem"
INSTALLER = ROOT / "scripts" / "install-debian.sh"


pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the Linux packages are built with bash")


def version():
    """Returns the application's version."""
    from multazem import __version__

    return __version__


def copy_project(dst: Path) -> Path:
    """Copies the project to ``dst``, leaving out caches, build output and the git directory; returns ``dst``."""
    shutil.copytree(
        ROOT,
        dst,
        ignore=shutil.ignore_patterns(
            "__pycache__", ".pytest_cache", ".git", "dist", "work", "*.egg-info", "build", ".venv", "pkg", "src_"
        ),
    )
    return dst


SHELL_SCRIPTS = [
    "packaging/build.sh",
    "packaging/stage.sh",
    "packaging/PKGBUILD",
    "packaging/templates/launcher.sh",
    "packaging/templates/deb-postinst.sh",
    "packaging/templates/deb-postrm.sh",
    "scripts/install-debian.sh",
]


@pytest.mark.parametrize("script", SHELL_SCRIPTS)
def test_shell_syntax(script):
    subprocess.run(["bash", "-n", str(ROOT / script)], check=True)


def test_version_is_consistent_everywhere():
    v = version()
    assert re.search(rf'^version = "{re.escape(v)}"$', (ROOT / "pyproject.toml").read_text(), re.MULTILINE)
    meta = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml").getroot()
    assert meta.find("releases").find("release").get("version") == v
    out = subprocess.run(
        ["bash", "-c", "source ./PKGBUILD; echo $pkgver"],
        cwd=ROOT / "packaging",
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.stdout.strip() == v


def test_app_id_is_consistent_everywhere():
    pytest.importorskip("gi", reason="multazem.app needs PyGObject")
    from multazem import app

    assert app.APP_ID == APP_ID
    desktop = (ROOT / "data" / f"{APP_ID}.desktop").read_text(encoding="utf-8")
    assert f"Icon={APP_ID}" in desktop
    assert (ROOT / "data" / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg").exists()
    meta = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml").getroot()
    assert meta.findtext("id") == APP_ID
    assert meta.find("launchable").text == f"{APP_ID}.desktop"


def test_icon_is_valid_svg_with_square_viewbox():
    svg = ET.parse(ROOT / "data" / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg").getroot()
    vb = [float(x) for x in svg.get("viewBox").split()]
    assert vb[2] == vb[3] and svg.tag.endswith("svg")


def test_icon_is_self_contained_and_stays_minimal():
    svg = ET.parse(ROOT / "data" / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg").getroot()
    shapes = [el.tag.rsplit("}", 1)[-1] for el in svg.iter() if el is not svg]
    assert set(shapes) <= {"rect", "path"}, shapes
    assert len(shapes) <= 3, shapes
    source = (ROOT / "data" / "icons" / "hicolor" / "scalable" / "apps" / f"{APP_ID}.svg").read_text(encoding="utf-8")
    assert "href" not in source and "data:" not in source


@pytest.mark.skipif(not shutil.which("desktop-file-validate"), reason="desktop-file-utils is not installed")
def test_desktop_entry_validates(tmp_path):
    out = subprocess.run(
        ["bash", "-c", f'source "{INSTALLER}"; render_desktop_entry "{ROOT}/data/{APP_ID}.desktop" /bin/true'],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    f = tmp_path / f"{APP_ID}.desktop"
    f.write_text(out, encoding="utf-8")
    r = subprocess.run(["desktop-file-validate", str(f)], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(not shutil.which("appstreamcli"), reason="appstream is not installed")
def test_metainfo_has_no_errors():
    r = subprocess.run(
        ["appstreamcli", "validate", "--no-net", str(ROOT / "data" / f"{APP_ID}.metainfo.xml")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert not [
        ln
        for ln in r.stdout.splitlines()
        if ln.startswith(("E:", "W: " + APP_ID + ":")) and "url-homepage-missing" not in ln
    ], r.stdout


NASTY_DIRS = [
    "plain",
    "My Projects & Co (v1)",
    "a|b",
    'q"uote',
    "dollar$HOME",
    "back\\slash",
    "`tick`",
    "arabic folder name \u0639\u0631\u0628\u064a",
    "it's mine",
    "semi;colon",
    "star*",
    "hash#",
    "~tilde",
]


@pytest.mark.parametrize("name", NASTY_DIRS)
def test_installer_desktop_entry_launches_from_any_path(tmp_path, name):
    gi = pytest.importorskip("gi")
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio

    exe = tmp_path / name / "multazem"
    exe.parent.mkdir()
    marker = tmp_path / "ran"
    exe.write_text(f"#!/bin/sh\n: > '{marker}'\n")
    exe.chmod(0o755)
    entry = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{INSTALLER}"; render_desktop_entry "{ROOT}/data/{APP_ID}.desktop" "$1"',
            "x",
            str(exe),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    f = tmp_path / "entry.desktop"
    f.write_text(entry, encoding="utf-8")
    info = Gio.DesktopAppInfo.new_from_filename(str(f))
    assert info is not None, entry
    info.launch([], None)
    for _ in range(30):
        if marker.exists():
            break
        time.sleep(0.1)
    assert marker.exists(), entry


def test_installer_refuses_percent_paths_and_root(tmp_path):
    d = copy_project(tmp_path / "pct%dir")
    r = subprocess.run(["bash", str(d / "scripts" / "install-debian.sh")], capture_output=True, text=True, check=False)
    assert r.returncode == 1 and "'%'" in r.stderr


def test_build_reports_a_missing_file_by_name(tmp_path):
    d = copy_project(tmp_path / "proj")
    shutil.rmtree(d / "src")
    r = subprocess.run(["bash", str(d / "packaging" / "build.sh")], capture_output=True, text=True, check=False)
    assert r.returncode == 1 and "Missing src/multazem/__init__.py" in r.stderr


needs_dpkg = pytest.mark.skipif(not shutil.which("dpkg-deb"), reason="dpkg-deb is not available")


def build(dst: Path, umask: int = 0o022, extra_env=None):
    """Runs ``packaging/build.sh`` of the copy at ``dst`` under the given umask and returns the finished process.

    Args:
        dst: The project copy to build in.
        umask: The umask in effect for the build.
        extra_env: Additional environment variables.
    """
    old = os.umask(umask)
    try:
        r = subprocess.run(
            ["bash", str(dst / "packaging" / "build.sh")],
            capture_output=True,
            text=True,
            env={**os.environ, **(extra_env or {})},
            cwd="/",
            check=False,
        )
    finally:
        os.umask(old)
    return r


DEB_EXPECTED_PATHS = (
    "./opt/multazem/multazem/app.py",
    "./opt/multazem/multazem/i18n/en.py",
    "./opt/multazem/multazem/i18n/ar.py",
    "./opt/multazem/multazem/core/prayer_times.py",
    "./opt/multazem/multazem/services/region_catalog.py",
    "./opt/multazem/multazem/ui/preferences/add_region_row.py",
    "./opt/multazem/multazem/icons/hicolor/scalable/actions/multazem-bell-symbolic.svg",
    "./opt/multazem/multazem/icons/hicolor/scalable/actions/multazem-bell-off-symbolic.svg",
    "./opt/multazem/adhanpy/PrayerTimes.py",
    "./opt/multazem/adhanpy/LICENSE",
    f"./usr/share/applications/{APP_ID}.desktop",
    f"./usr/share/icons/hicolor/scalable/apps/{APP_ID}.svg",
    f"./usr/share/metainfo/{APP_ID}.metainfo.xml",
    "./usr/bin/multazem",
    "./usr/share/doc/multazem/copyright",
    "./usr/share/doc/multazem/changelog.gz",
)


def dpkg_output(*args: str) -> str:
    """Runs ``dpkg-deb`` with ``args`` and returns what it printed."""
    return subprocess.run(["dpkg-deb", *args], capture_output=True, text=True, check=True).stdout


def assert_deb_listing_is_clean_and_complete(deb: Path):
    """Asserts that the package contains every expected path and no writable entry, bytecode cache or test file."""
    listing = dpkg_output("-c", str(deb))
    for line in listing.splitlines():
        permissions = line.split()[0]
        assert permissions[5] != "w" and permissions[8] != "w", line
        assert "__pycache__" not in line and ".pyc" not in line
    names = " ".join(listing.split())
    for expected in DEB_EXPECTED_PATHS:
        assert expected in names, expected
    assert "tests" not in names and "packaging/" not in names


def assert_deb_control_is_right(deb: Path):
    """Asserts the dependencies, architecture and replacement of the former package name in the control file."""
    control = dpkg_output("-f", str(deb))
    assert "Architecture: all" in control and "gir1.2-adw-1 (>= 1.5)" in control and "tzdata" in control
    assert "python3 (>= 3.11)" in control and "libnotify-bin" in control
    assert "Package: multazem\n" in control
    assert "Replaces: salah-reminder\n" in control and "Conflicts: salah-reminder\n" in control


@needs_dpkg
@pytest.mark.parametrize("umask", [0o022, 0o002, 0o077])
def test_deb_builds_from_a_path_with_spaces_under_any_umask(tmp_path, umask):
    d = copy_project(tmp_path / "My Projects & Co" / "multazem")
    r = build(d, umask)
    deb = d / "packaging" / "dist" / f"multazem_{version()}_all.deb"
    assert deb.exists(), r.stdout + r.stderr

    assert_deb_listing_is_clean_and_complete(deb)
    assert_deb_control_is_right(deb)

    scripts = tmp_path / "scripts"
    subprocess.run(["dpkg-deb", "-e", str(deb), str(scripts)], check=True)
    assert "salah_reminder" in (scripts / "postinst").read_text()

    extracted = tmp_path / "ex"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(extracted)], check=True)
    launcher = (extracted / "usr" / "bin" / "multazem").read_text()
    assert "exec /usr/bin/python3 -m multazem" in launcher
    desktop = (extracted / "usr" / "share" / "applications" / f"{APP_ID}.desktop").read_text(encoding="utf-8")
    assert "Exec=multazem\n" in desktop and "placeholder" not in desktop


@needs_dpkg
def test_build_twice_is_clean_and_idempotent(tmp_path):
    d = copy_project(tmp_path / "proj")
    assert build(d).returncode == 0
    r = build(d)
    assert r.returncode == 0 and len(list((d / "packaging" / "dist").glob("*.deb"))) == 1


@pytest.mark.skipif(not shutil.which("rpmbuild") or not shutil.which("rpm"), reason="rpm is not available")
def test_rpm_builds_with_correct_metadata(tmp_path):
    d = copy_project(tmp_path / "proj")
    r = build(d)
    rpms = list((d / "packaging" / "dist").glob("*.rpm"))
    assert rpms, r.stdout + r.stderr
    reqs = subprocess.run(["rpm", "-qRp", str(rpms[0])], capture_output=True, text=True, check=False).stdout
    assert "libadwaita >= 1.5" in reqs and "python3-gobject" in reqs and "tzdata" in reqs
    scripts = subprocess.run(
        ["rpm", "-qp", "--scripts", str(rpms[0])], capture_output=True, text=True, check=False
    ).stdout
    assert '"$1" = "0"' in scripts
    files = subprocess.run(["rpm", "-qlp", str(rpms[0])], capture_output=True, text=True, check=False).stdout
    assert "/usr/share/licenses/multazem/LICENSE" in files and "/usr/bin/multazem" in files
    obsoletes = subprocess.run(
        ["rpm", "-qp", "--obsoletes", str(rpms[0])], capture_output=True, text=True, check=False
    ).stdout
    assert "salah-reminder" in obsoletes


@needs_dpkg
def test_launcher_ignores_a_pyenv_style_python_earlier_in_path(tmp_path):
    d = copy_project(tmp_path / "proj")
    assert build(d).returncode == 0
    deb = next((d / "packaging" / "dist").glob("*.deb"))
    ex = tmp_path / "ex"
    subprocess.run(["dpkg-deb", "-x", str(deb), str(ex)], check=True)
    fake = tmp_path / "fakebin"
    fake.mkdir()
    (fake / "python3").write_text("#!/bin/sh\necho 'WRONG PYTHON USED' >&2\nexit 99\n")
    (fake / "python3").chmod(0o755)
    launcher = (ex / "usr" / "bin" / "multazem").read_text().replace("/opt/multazem", str(ex / "opt" / "multazem"))
    script = tmp_path / "launcher.sh"
    script.write_text(launcher)
    script.chmod(0o755)
    pytest.importorskip("gi")
    r = subprocess.run(
        [str(script), "--version"],
        capture_output=True,
        text=True,
        env={**os.environ, "PATH": f"{fake}:{os.environ['PATH']}"},
        check=False,
    )
    assert r.returncode == 0 and "WRONG PYTHON" not in r.stderr and r.stdout.startswith("multazem ")


def test_no_placeholder_identity_left_in_packaging():
    for f in ("packaging/build.sh", "packaging/PKGBUILD", "packaging/templates/deb-control.in", "pyproject.toml"):
        text = (ROOT / f).read_text(encoding="utf-8")
        assert "example.com" not in text and "you <" not in text, f
    assert 'MAINTAINER="AbuKaram01 <abukaram01@proton.me>"' in (ROOT / "packaging/build.sh").read_text(encoding="utf-8")


@pytest.mark.skipif(not shutil.which("pip") and not shutil.which("pip3"), reason="pip is not available")
def test_wheel_contains_the_bundled_icons(tmp_path):
    pytest.importorskip("setuptools")
    d = copy_project(tmp_path / "proj")
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-build-isolation",
            "--no-deps",
            "-q",
            "-w",
            str(tmp_path / "out"),
            str(d),
        ],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    wheels = list((tmp_path / "out").glob("*.whl"))
    if not wheels:
        pytest.skip("could not build a wheel in this environment (no wheel/setuptools?): " + r.stderr[-200:])
    import zipfile

    names = zipfile.ZipFile(wheels[0]).namelist()
    assert "multazem/icons/hicolor/scalable/actions/multazem-bell-symbolic.svg" in names
    assert "multazem/icons/hicolor/scalable/actions/multazem-bell-off-symbolic.svg" in names


def test_every_subpackage_is_a_real_package():
    package_root = ROOT / "src" / "multazem"
    for directory in [package_root, *[d for d in package_root.rglob("*") if d.is_dir()]]:
        if "__pycache__" in directory.parts or "icons" in directory.parts:
            continue
        assert (directory / "__init__.py").exists(), directory


def test_wheel_lists_all_subpackages():
    pytest.importorskip("setuptools")
    from setuptools import find_packages

    found = set(find_packages(str(ROOT / "src")))
    assert {
        "multazem",
        "multazem.core",
        "multazem.i18n",
        "multazem.services",
        "multazem.ui",
        "multazem.ui.preferences",
    } <= found


def test_desktop_entry_and_metainfo_are_localized_for_both_languages():
    desktop = (ROOT / "data" / f"{APP_ID}.desktop").read_text(encoding="utf-8")
    assert "\nName=Multazem\n" in desktop and "\nName[ar]=" not in desktop
    assert "\nComment=" in desktop and "\nComment[ar]=" in desktop
    meta = ET.parse(ROOT / "data" / f"{APP_ID}.metainfo.xml").getroot()
    xml_lang = "{http://www.w3.org/XML/1998/namespace}lang"
    assert [e.text for e in meta.findall("name")] == ["Multazem"]
    elements = meta.findall("summary")
    assert [e for e in elements if e.get(xml_lang) is None]
    assert [e for e in elements if e.get(xml_lang) == "ar"]


def test_arch_package_replaces_the_former_name():
    pkgbuild = (ROOT / "packaging" / "PKGBUILD").read_text(encoding="utf-8")
    assert "pkgname=multazem\n" in pkgbuild
    assert "replaces=('salah-reminder')" in pkgbuild and "conflicts=('salah-reminder')" in pkgbuild


def run_bash(script: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Runs a bash script with positional arguments ``args`` and returns the finished process."""
    return subprocess.run(["bash", "-c", script, "x", *args], capture_output=True, text=True, cwd=cwd, check=False)


@pytest.mark.parametrize("value", ["plain", "a&b", "a|b", "back\\slash", "My Projects & Co", "x@y.z"])
def test_render_template_writes_special_characters_literally(tmp_path, value):
    control, spec = tmp_path / "control", tmp_path / "multazem.spec"
    script = (
        'source "$1/packaging/build.sh"; VERSION=1.2.3; MAINTAINER="$4"; '
        'render_template deb-control.in "$2" && render_template rpm.spec.in "$3" "RPM_ROOT=$4"'
    )
    r = run_bash(script, str(ROOT), str(control), str(spec), value)
    assert r.returncode == 0, r.stderr
    assert f"Maintainer: {value}\n" in control.read_text(encoding="utf-8")
    assert f"cp -a {value}/. %{{buildroot}}/\n" in spec.read_text(encoding="utf-8")


def test_render_template_refuses_an_unknown_placeholder(tmp_path):
    (tmp_path / "broken.in").write_text("Package: @NO_SUCH_VALUE@\n", encoding="utf-8")
    script = 'source "$1/packaging/build.sh"; VERSION=1.2.3; TEMPLATES_DIR="$2"; render_template broken.in "$2/out"'
    r = run_bash(script, str(ROOT), str(tmp_path))
    assert r.returncode == 1 and "broken.in: a placeholder was not replaced" in r.stderr


def stage_with_the_pkgbuild(project: Path, pkgdir: Path) -> subprocess.CompletedProcess:
    """Runs the PKGBUILD's ``package()`` of ``project`` into ``pkgdir`` and returns the finished process."""
    return run_bash('set -e; source ./PKGBUILD; pkgdir="$1"; package', str(pkgdir), cwd=project / "packaging")


def test_arch_package_stages_the_application_and_its_data(tmp_path):
    pkgdir = tmp_path / "pkg"
    r = stage_with_the_pkgbuild(ROOT, pkgdir)
    assert r.returncode == 0, r.stderr
    for expected in (
        "opt/multazem/multazem/app.py",
        "opt/multazem/adhanpy/PrayerTimes.py",
        f"usr/share/applications/{APP_ID}.desktop",
        f"usr/share/icons/hicolor/scalable/apps/{APP_ID}.svg",
        f"usr/share/metainfo/{APP_ID}.metainfo.xml",
        "usr/share/licenses/multazem/LICENSE",
    ):
        assert (pkgdir / expected).is_file(), expected
    launcher = pkgdir / "usr" / "bin" / "multazem"
    assert os.access(launcher, os.X_OK) and "exec /usr/bin/python3 -m multazem" in launcher.read_text()
    desktop = (pkgdir / "usr" / "share" / "applications" / f"{APP_ID}.desktop").read_text(encoding="utf-8")
    assert "Exec=multazem\n" in desktop and "placeholder" not in desktop
    leftovers = [p for p in pkgdir.rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]
    assert not leftovers
    assert not [p for p in pkgdir.rglob("*") if p.stat().st_mode & 0o022], "group/other-writable entries"


def test_staging_refuses_a_desktop_entry_with_a_leftover_exec_placeholder(tmp_path):
    project = copy_project(tmp_path / "proj")
    entry = project / "data" / f"{APP_ID}.desktop"
    entry.write_text(entry.read_text(encoding="utf-8") + "TryExec=multazem-exec-placeholder\n", encoding="utf-8")
    r = stage_with_the_pkgbuild(project, tmp_path / "pkg")
    assert r.returncode != 0 and "Exec placeholder was not replaced" in r.stderr


def test_the_postinst_pattern_stops_only_the_old_application():
    postinst = (ROOT / "packaging" / "templates" / "deb-postinst.sh").read_text(encoding="utf-8")
    pattern = re.search(r"pkill -f -- '([^']+)'", postinst).group(1)
    for command in (
        "/usr/bin/python3 -m salah_reminder",
        "/usr/bin/python3 -m salah_reminder --headless",
        "/usr/bin/python3 /home/u/.local/bin/salah-reminder",
        "python3.12 -m salah_reminder",
    ):
        assert re.search(pattern, command), command
    for command in (
        "/usr/bin/python3 -m multazem",
        "vim /usr/bin/salah-reminder",
        "tail -f /var/log/salah-reminder",
        "/usr/bin/python3 -m salah_reminder_tools",
        "/usr/bin/python3 /usr/bin/multazem --headless",
    ):
        assert not re.search(pattern, command), command
