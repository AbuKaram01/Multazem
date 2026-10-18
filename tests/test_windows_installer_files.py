# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Checks on the files of the Windows installer.

Those are the Inno Setup script, the PowerShell scripts, and what the installer carries (the GTK runtime, Python and
the Python libraries).
"""

import re
import subprocess

import pytest

import multazem
from multazem.services import windows_toast

from packaging_support import APP_ID, ROOT, WINDOWS, needs_pwsh, read

POWERSHELL_SCRIPTS = [
    ROOT / "scripts" / "install-windows.ps1",
    ROOT / "scripts" / "uninstall-windows.ps1",
    ROOT / "packaging" / "build-windows.ps1",
    ROOT / "scripts" / "gtk-portable.ps1",
    ROOT / "scripts" / "python-bundle.ps1",
    WINDOWS / "check-installed.ps1",
    WINDOWS / "run-installer.ps1",
]


def test_the_windows_icon_and_installer_files_exist():
    assert (ROOT / "data" / "windows" / "multazem.ico").is_file()
    assert (WINDOWS / "multazem.iss").is_file()
    assert (WINDOWS / "dlls.py").is_file()
    for script in POWERSHELL_SCRIPTS:
        assert script.is_file(), script


def test_the_installer_script_matches_the_package_version_and_app_id():
    text = read(WINDOWS / "multazem.iss")
    assert f'#define AppVersion "{multazem.__version__}"' in text
    assert f'#define AppId "{APP_ID}"' in text
    assert windows_toast.APP_USER_MODEL_ID == APP_ID
    # The build reads the version it hands to Inno Setup from pyproject.toml.
    assert re.search(rf'(?m)^version\s*=\s*"{re.escape(multazem.__version__)}"', read(ROOT / "pyproject.toml"))


def test_the_installer_runs_the_install_script_per_user_and_cleans_up_after_itself():
    text = read(WINDOWS / "multazem.iss")
    assert "PrivilegesRequired=lowest" in text
    assert "scripts\\install-windows.ps1" in text and "-NoShortcut" in text
    assert "{localappdata}\\multazem\\gtk" in text and "{app}\\.venv" in text
    assert "-m multazem" in text
    deletions = [
        line.lower()
        for line in text.split("[UninstallDelete]")[1].split("[Code]")[0].splitlines()
        if line.strip() and not line.startswith(";")
    ]
    # The settings and the saved regions (in %APPDATA%\multazem) and the log (in %LOCALAPPDATA%\multazem) are the
    # user's: of the folder in %LOCALAPPDATA% only the downloaded GTK runtime goes.
    assert not any("{userappdata}" in line or "{%" in line for line in deletions)
    local = [line for line in deletions if "{localappdata}" in line]
    assert len(local) == 1 and local[0].endswith('multazem\\gtk"'), local
    for kept in ("settings", "regions", "multazem.log", "install.log"):
        assert not any(kept in line for line in deletions), kept


def test_autostart_is_an_installer_task_that_is_off_by_default_like_the_button_it_stands_for():
    text = read(WINDOWS / "multazem.iss")
    task = next(line for line in text.splitlines() if line.startswith('Name: "autostart"'))
    assert "Flags: unchecked" in task
    # The task passes -Autostart on, and so does an upgrade of an installation that had the reminders on.
    assert "WizardIsTaskSelected('autostart') or RemindersWereOn" in text
    assert "' -Autostart'" in text
    # What "on" means is what the program itself writes: the Run value named Multazem.
    assert "Software\\Microsoft\\Windows\\CurrentVersion\\Run', 'Multazem'" in text


def test_an_upgrade_stops_the_background_process_before_the_files_are_replaced():
    text = read(WINDOWS / "multazem.iss")
    prepare = text.split("function PrepareToInstall")[1].split("end;")[0]
    assert prepare.index("RemindersWereOn := RemindersAreOn") < prepare.index("RunUninstallScript('-StopOnly')")
    uninstall = read(ROOT / "scripts" / "uninstall-windows.ps1")
    # -StopOnly ends the process and goes no further: the sign-in entry and the files are left for the upgrade.
    assert uninstall.index("Stop-BackgroundProcess\nif ($StopOnly) { exit 0 }") < uninstall.index("RunKey -Name")
    assert "CurUninstallStep = usUninstall" in text and "RunUninstallScript('-Force')" in text


def test_the_uninstall_script_stops_only_a_process_that_is_the_background_process_of_multazem():
    """A number left in background.pid after a crash may belong to another program by now."""
    uninstall = read(ROOT / "scripts" / "uninstall-windows.ps1")
    pattern = re.search(r"-match '([^']*multazem[^']*)'", uninstall)
    assert pattern, "the uninstall script does not look at the command line of the process it stops"
    from multazem.services import windows_service

    command = '"C:\\Users\\me\\AppData\\Local\\Programs\\Multazem\\.venv\\Scripts\\pythonw.exe" -m multazem --headless'
    assert re.search(pattern.group(1), command)
    assert re.search(pattern.group(1), " ".join(windows_service.background_command()))
    assert not re.search(pattern.group(1), '"C:\\Windows\\notepad.exe" notes.txt')
    assert not re.search(pattern.group(1), '"C:\\Python\\python.exe" -m multazem')  # The window, not the reminders.


def test_pygobject_is_not_requested_from_pypi_on_windows_and_tzdata_is():
    text = read(ROOT / "pyproject.toml")
    assert "PyGObject>=3.42; sys_platform != 'win32'" in text
    # Windows has no time zone database of its own, and the default region needs one.
    assert "tzdata; sys_platform == 'win32'" in text


def test_the_install_script_follows_the_runtime_that_the_application_looks_for():
    text = read(ROOT / "scripts" / "install-windows.ps1")
    portable = read(ROOT / "scripts" / "gtk-portable.ps1")  # Where Test-GtkRuntime lives.
    assert "'multazem'" in text and "'gtk'" in text  # %LOCALAPPDATA%\multazem\gtk, see winsupport.
    assert "MULTAZEM_GTK_DIR" in text and "-m multazem" in text
    assert "Adw-1.typelib" in portable
    assert "*adwaita-1-*.dll" in portable  # The DLL is adwaita-1-0.dll, not libadwaita-...


@pytest.mark.parametrize("name", ["install-windows.ps1", "uninstall-windows.ps1"])
def test_the_windows_scripts_refuse_to_run_elsewhere_with_a_clear_message(name):
    text = read(ROOT / "scripts" / name)
    assert "$env:OS -ne 'Windows_NT'" in text and "This script is for Windows" in text
    # The check has to come before anything that needs Windows.
    assert text.index("Windows_NT") < text.index("$env:LOCALAPPDATA")


@pytest.mark.parametrize("script", POWERSHELL_SCRIPTS, ids=lambda path: path.name)
def test_every_powershell_script_is_plain_ascii(script):
    """Windows PowerShell 5.1 reads a script without a byte order mark in the machine's code page."""
    assert script.read_bytes().isascii(), f"{script.name} has a character that is not ASCII"


@needs_pwsh
@pytest.mark.parametrize("script", POWERSHELL_SCRIPTS, ids=lambda path: path.name)
def test_every_powershell_script_parses(script, tmp_path):
    checker = tmp_path / "parse.ps1"
    checker.write_text(
        "param($Path)\n"
        "$errors = $null; $tokens = $null\n"
        "[System.Management.Automation.Language.Parser]::ParseFile($Path, [ref]$tokens, [ref]$errors) | Out-Null\n"
        "if ($errors.Count) { $errors | ForEach-Object { Write-Output $_.Message }; exit 1 }\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(checker), str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout


def test_the_windows_icon_ships_with_the_sources():
    icon = ROOT / "data" / "windows" / "multazem.ico"
    assert icon.read_bytes()[:4] == b"\x00\x00\x01\x00"  # An ICO header with at least one image.


# --- The GTK runtime inside the Windows installer ---


def test_the_windows_installer_carries_the_gtk_runtime_when_one_was_prepared():
    text = read(WINDOWS / "multazem.iss")
    assert "#if DirExists(GtkFolder)" in text and 'DestDir: "{app}\\gtk"' in text
    assert 'gtk-portable.ps1"; DestDir: "{app}\\scripts"' in text  # The install script needs it.
    # An upgrade replaces the runtime as a whole, so no file of an older one stays beside the new DLLs ...
    assert 'Type: filesandordirs; Name: "{app}\\gtk"' in text.split("[InstallDelete]")[1].split("[Icons]")[0]
    # ... and the uninstaller removes it, with the one an install script run by hand downloaded.
    removed = text.split("[UninstallDelete]")[1].split("[Code]")[0]
    assert '"{app}\\gtk"' in removed and '"{localappdata}\\multazem\\gtk"' in removed


def test_the_build_prepares_the_gtk_runtime_afresh_and_can_pin_it():
    build = read(ROOT / "packaging" / "build-windows.ps1")
    assert "Get-PortableGtk" in build and "gtk-portable.ps1" in build
    for option in ("NoGtk", "GtkTag", "GtkSha256", "GtkZip"):
        assert f"${option}" in build, option
    assert build.index("Remove-Item $gtkBundle") < build.index("Get-PortableGtk -Target")  # Never an old runtime.
    assert "/packaging/gtk/" in read(ROOT / ".gitignore")


def test_the_install_script_uses_the_runtime_inside_the_installer_before_downloading_one():
    install = read(ROOT / "scripts" / "install-windows.ps1")
    assert "gtk-portable.ps1" in install and "Resolve-GtkChoice" in install
    assert "function Test-GtkRuntime" not in install  # One definition, in gtk-portable.ps1.
    assert install.index("Resolve-GtkChoice -Explicit") < install.index("Get-PortableGtk -Target $GtkDir")
    # The bundled runtime is found by itself: nothing to save.
    assert "$CustomGtk   = $gtkChoice.Custom" in install


def test_the_gtk_download_is_checked_before_it_is_used():
    text = read(ROOT / "scripts" / "gtk-portable.ps1")
    assert "github.com/wingtk/gvsbuild/releases/download/$resolved/$asset" in text
    assert "Get-FileHash" in text and "does not match the expected SHA256" in text
    assert "digest" in text and "gvsbuild-release.txt" in text


def test_nothing_the_application_loads_is_on_the_list_of_what_the_build_leaves_out():
    """The build tools and C++ bindings go; the C libraries, GLib's helper programs and the schema compiler stay."""
    text = read(ROOT / "scripts" / "gtk-portable.ps1")
    removed = text.split("$script:GtkDevelopmentFolders")[1].split("# --- Choosing a runtime")[0]
    removed = "\n".join(line for line in removed.splitlines() if not line.lstrip().startswith("#"))
    for needed in (
        "gspawn-win64-helper",
        "glib-compile-schemas",
        "gdk-pixbuf",
        "girepository-1.0",
        "share\\icons",
        "share\\glib-2.0",
        "share\\locale",
    ):
        assert needed not in removed.replace("lib\\gobject-introspection", ""), needed
    assert "'lib\\gobject-introspection'" in removed  # The scanner, not the typelibs that GTK loads.
