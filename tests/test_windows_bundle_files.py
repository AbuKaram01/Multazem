# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The Windows scripts and CI agree on how the bundled Python and wheelhouse are used.

Checks that the install script, the Inno Setup script, the build and CI use the bundled Python and wheelhouse the way
the tests of scripts/python-bundle.ps1 assume.
"""

from packaging_support import BUNDLE, CI, ROOT, WINDOWS, read


def test_the_install_script_prefers_what_the_installer_carries_and_falls_back_to_the_internet():
    install = read(ROOT / "scripts" / "install-windows.ps1")
    assert ". (Join-Path $PSScriptRoot 'python-bundle.ps1')" in install
    # Python comes from the installer that ships with Multazem; winget is only the fallback.
    python_step = install.split("function Install-Python")[1].split("$wheelDir =")[0]
    assert (
        python_step.index("Find-PythonInstaller")
        < python_step.index("Install-PythonFromInstaller")
        < python_step.index("winget install")
    )
    assert "installer that came with Multazem" in python_step
    # The libraries are installed from the wheelhouse, without an index, when it was built for this Python; if that
    # fails, they are downloaded as before.
    assert "$offline = Test-Wheelhouse $wheelhouse $chosen" in install
    assert "if (-not $offline) { Pip @('install', '--upgrade', 'pip', '--quiet') }" in install
    assert install.count("'--no-index', '--find-links', $wheelhouse") == 1
    assert "installed from the wheelhouse (no internet needed)" in install
    assert "downloading them instead" in install and "Pip @('install', '--quiet', '-e', $ProjectRoot)" in install


def test_pygobject_and_pycairo_come_from_the_gtk_runtime_not_from_the_wheelhouse_or_the_internet():
    install = read(ROOT / "scripts" / "install-windows.ps1")
    wheels = install.split("Installing PyGObject and pycairo")[1].split("# --- 4. Multazem itself")[0]
    assert "--force-reinstall" in wheels and "$cairo.FullName, $gobject.FullName" in wheels
    # They are installed before the project, so that the project's own requirement (none on Windows) finds them.
    assert install.index("Installing PyGObject and pycairo") < install.index("Installing Multazem and its Python")
    # The wheelhouse is checked for what the program imports, not for them.
    check = read(BUNDLE).split("function Get-WheelhouseProblem")[1].split("function Test-Wheelhouse")[0]
    assert "'adhanpy-', 'tzdata-', 'setuptools-'" in check
    assert "pygobject" not in check.lower()


def test_the_build_prepares_python_and_its_libraries_for_the_python_of_the_gtk_runtime():
    build = read(ROOT / "packaging" / "build-windows.ps1")
    assert ". (Join-Path $ProjectRoot 'scripts\\python-bundle.ps1')" in build
    assert "[switch]$NoPython" in build and "[string]$PythonExe" in build and "[string]$PythonInstaller" in build
    assert (
        "[switch]$RequirePython" in build
        and 'throw "-RequirePython: $Message"' in build
        and build.count("Skip-PythonPart ") >= 4
    )
    # A reason is recorded for the Python installer and another for the libraries.
    assert build.count("$script:BundleProblem") == 2
    assert (
        build.index("Get-PortableGtk -Target $gtkBundle")
        < build.index("$minor = Get-GtkPythonMinor")
        < build.index("Get-PythonInstaller -Target (Join-Path")
        < build.index("& $compiler")
    )
    # The wheels are built for the Python of the GTK runtime.
    assert "-ExpectMinor $minor" in build
    # The Python installer that is bundled has the version of the Python that runs the build.
    assert "platform.python_version()" in build
    ignore = read(ROOT / ".gitignore")
    assert "/packaging/python/" in ignore and "/packaging/wheelhouse/" in ignore


def test_the_build_has_no_switch_for_a_visual_cpp_runtime_because_the_installer_carries_none():
    """Leaves the Visual C++ runtime out of the installer.

    GTK, libadwaita and PyGObject need only vcruntime140.dll and vcruntime140_1.dll, which Python's own installer
    puts beside python.exe (the scan in packaging/windows/dlls.py proves it on the real runtime).
    """
    build = read(ROOT / "packaging" / "build-windows.ps1")
    assert "VcRuntime" not in build and "vcruntime-bundle" not in build
    assert "vcruntime" not in read(WINDOWS / "multazem.iss").lower()
    assert "RequireVcRuntime" not in read(CI)


def test_the_inno_script_carries_python_and_the_wheelhouse_only_when_the_build_prepared_them():
    iss = read(WINDOWS / "multazem.iss")
    assert 'Source: "..\\..\\scripts\\python-bundle.ps1"; DestDir: "{app}\\scripts"' in iss
    for folder, define in (("python", "PythonFolder"), ("wheelhouse", "WheelFolder")):
        assert f'#define {define} SourcePath + "\\..\\{folder}"' in iss
        assert (
            f'#if DirExists({define})\nSource: "{{#{define}}}\\*"; DestDir: "{{app}}\\{folder}"; '
            f"Flags: recursesubdirs ignoreversion\n#endif"
        ) in iss
        # The folder is replaced on an upgrade (InstallDelete) and removed on uninstall (UninstallDelete).
        assert f'Type: filesandordirs; Name: "{{app}}\\{folder}"' in iss
    assert iss.count('Name: "{app}\\python"') == 2 and iss.count('Name: "{app}\\wheelhouse"') == 2
    # The section header sits outside the conditionals, so the section exists whichever folders are present.
    assert "[InstallDelete]\n#if DirExists(GtkFolder)" in iss


def test_the_installation_check_knows_what_the_install_script_says_when_it_used_the_bundled_parts():
    check = read(WINDOWS / "check-installed.ps1")
    install = read(ROOT / "scripts" / "install-windows.ps1")
    for marker in (
        "Python libraries installed from the wheelhouse",
        "installer that came with Multazem",
        "downloading them instead",
        "recreating it",
    ):
        assert marker in install, marker
    for marker in (
        "Python libraries installed from the wheelhouse",
        "installer that came with Multazem",
        "downloading them instead",
    ):
        assert marker in check, marker
    assert "Installing Python $Version with winget" in install and "with winget" in check
    # The check looks for the same libraries that the wheelhouse is checked for.
    for library in ("adhanpy", "tzdata", "setuptools"):
        assert f"'{library}'" in check


def test_the_installation_check_loads_the_libraries_with_and_without_a_console():
    checker = read(WINDOWS / "check-installed.ps1")
    section = checker.split("# 4b.")[1].split("# 5. The application starts")[0]
    # The runtime support comes first, as it does when the program starts, then every library that needs native DLLs.
    probe = section.split("$libraryProbeSource")[1].split("'@")[0]
    assert probe.index("import multazem.app") < probe.index("import cairo") < probe.index("import gi")
    for library in ("adhanpy", "cairo", "gi", "zoneinfo"):
        assert library in probe, library
    # The check runs the program with a console (python.exe) and, as the Start menu does, without one (pythonw.exe).
    assert "'python.exe', 'pythonw.exe'" in section
    assert checker.index("# 4. GTK loads") < checker.index("# 4b.") < checker.index("# 5. The application starts")
