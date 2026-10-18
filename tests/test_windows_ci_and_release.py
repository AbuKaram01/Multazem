# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""Which GTK release is used, what the CI jobs run, and what they leave behind when an installation fails."""

import re

import pytest

from packaging_support import CI, ROOT, WINDOWS, read

yaml = pytest.importorskip("yaml", reason="PyYAML reads the workflow")

EVERY_PUSH = ["linux", "windows-core", "windows-gtk", "installer"]
MANUAL_ONLY = ["windows-installer-run", "windows-full-install"]


def workflow() -> dict:
    """Returns the workflow, as YAML makes of it."""
    return yaml.safe_load(read(CI))


def step_text(step: dict) -> str:
    """Returns the text of a step: its script as written, then its other settings."""
    settings = {key: value for key, value in step.items() if key != "run"}
    return step.get("run", "") + "\n" + yaml.safe_dump(settings, sort_keys=False, width=10_000)


def steps_text(job: str, step_name: str) -> str:
    """Returns the text of the step ``step_name`` of ``job``: its ``run`` script and its settings."""
    for step in workflow()["jobs"][job]["steps"]:
        if step.get("name", "").startswith(step_name):
            return step_text(step)
    raise AssertionError(f"{job} has no step named {step_name!r}")


def test_the_workflow_has_the_jobs_that_run_on_every_push_and_the_two_that_only_run_by_hand():
    jobs = workflow()["jobs"]
    assert list(jobs) == EVERY_PUSH + MANUAL_ONLY
    for name in EVERY_PUSH:
        assert jobs[name]["if"] == "github.event_name != 'workflow_dispatch'", name
    for name in MANUAL_ONLY:
        assert jobs[name]["if"] == "github.event_name == 'workflow_dispatch'", name
    triggers = workflow()[True]  # YAML reads the key "on" as true.
    assert set(triggers) == {"push", "pull_request", "workflow_dispatch"}


def test_the_installer_waits_for_the_cheaper_windows_job():
    assert workflow()["jobs"]["installer"]["needs"] == "windows-core"


def test_the_gtk_release_is_a_tested_one_and_not_the_newest():
    portable = read(ROOT / "scripts" / "gtk-portable.ps1")
    # gvsbuild 2026.10.0 builds its PyGObject wheels for Python 3.15; 2026.8.0 has them for 3.14, which is what CI uses.
    assert "$script:GtkDefaultTag = '2026.8.0'" in portable
    versions = set(re.findall(r'python-version: "([^"]+)"', read(CI)))
    assert versions == {"3.12", "3.14"}  # 3.12 only for the job that has no GTK.
    install = read(ROOT / "scripts" / "install-windows.ps1")
    assert "Get-GtkZipUrls" not in install
    assert "releases/latest" not in install  # No "newest" lookup of its own.
    assert "[string]$GtkTag" in install and "-Tag $GtkTag" in install
    assert "[string]$GtkTag = ''" in read(ROOT / "packaging" / "build-windows.ps1")
    assert "-PythonVersion 3.14" in read(CI) and "-PythonVersion 3.10" not in read(CI)


def test_a_wheel_mismatch_says_which_python_the_wheels_are_for():
    install = read(ROOT / "scripts" / "install-windows.ps1")
    assert "are for Python $($available -join ', ')" in install
    assert "-GtkTag" in install


def test_the_installer_keeps_a_log_of_the_install_script_and_points_to_it():
    install = read(ROOT / "scripts" / "install-windows.ps1")
    assert "[string]$LogFile" in install and "Start-Transcript" in install
    iss = read(WINDOWS / "multazem.iss")
    assert "-LogFile" in iss and "multazem\\install.log" in iss
    assert iss.count("install.log") >= 2  # Passed to the script, named in the error.


def test_the_linux_job_runs_the_linters_and_the_whole_suite_under_a_virtual_display():
    job = workflow()["jobs"]["linux"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    for needed in (".venv/bin/ruff check .", ".venv/bin/ruff format --check .", "shellcheck", "xvfb-run", "pytest -q"):
        assert needed in commands, needed
    assert "python3-gi" in commands and "gir1.2-adw-1" in commands
    assert "--system-site-packages" in commands  # PyGObject is the distribution's, not PyPI's.


def test_the_windows_core_job_parses_the_scripts_in_the_powershell_that_users_have():
    job = workflow()["jobs"]["windows-core"]
    parse = next(step for step in job["steps"] if "parse" in step.get("name", ""))
    assert parse["shell"] == "powershell"  # Windows PowerShell 5.1, which runs the scripts when the installer does.
    assert "ParseFile" in parse["run"] and "scripts, packaging" in parse["run"]
    commands = "\n".join(step.get("run", "") for step in job["steps"])
    assert "pip install adhanpy tzdata pytest pyyaml ruff" in commands  # tzdata: Windows has no time zone database.


def test_only_the_job_with_the_real_install_may_change_the_registry_of_the_runner():
    jobs = workflow()["jobs"]
    test_step = steps_text("windows-gtk", "Test")
    assert "MULTAZEM_REAL_WINDOWS_TESTS: '1'" in test_step
    assert "MULTAZEM_REAL_WINDOWS_TESTS" in read(ROOT / "tests" / "test_windows_real.py")
    for name in ("linux", "windows-core", "installer", "windows-installer-run", "windows-full-install"):
        assert "MULTAZEM_REAL_WINDOWS_TESTS" not in "\n".join(step_text(step) for step in jobs[name]["steps"]), name


def test_the_installer_job_checks_the_pruned_runtime_python_and_the_wheelhouse():
    build = steps_text("installer", "Build the installer")
    assert "./packaging/build-windows.ps1 -RequirePython" in build
    runtime = steps_text("installer", "The installer carries the GTK runtime")
    for needed in ("Test-GtkRuntime", "pygobject*.whl", "*.pdb", "protoc.exe", "-gt 400MB", "'include'"):
        assert needed in runtime, needed
    carries = steps_text("installer", "The installer carries the Python installer and the Python libraries")
    assert "Find-PythonInstaller" in carries and "Test-Wheelhouse 'packaging\\wheelhouse'" in carries
    assert "throw" in carries
    # The libraries are collected with the Python of the GTK runtime, so the job must provide that Python.
    setup = next(step for step in workflow()["jobs"]["installer"]["steps"] if "setup-python" in step.get("uses", ""))
    assert setup["with"]["python-version"] == "3.14"
    assert workflow()["jobs"]["installer"]["steps"][-1]["with"]["name"] == "multazem-windows-setup"


def test_the_installers_built_in_ci_must_carry_python_or_the_build_says_why():
    ci = read(CI)
    # The installer job and windows-installer-run both build with -RequirePython.
    assert ci.count("run: ./packaging/build-windows.ps1 -RequirePython\n") == 2
    # No other build omits it: an installer that quietly lacks Python or its libraries would only fail much later.
    assert "run: ./packaging/build-windows.ps1\n" not in ci
    assert "RequireVcRuntime" not in ci


def test_the_manual_installer_job_cannot_hang_and_shows_the_logs():
    job = workflow()["jobs"]["windows-installer-run"]
    assert job["timeout-minutes"] == 60
    runs = [step for step in job["steps"] if "run-installer.ps1" in step.get("run", "")]
    assert len(runs) == 2 and all(step["timeout-minutes"] == 35 for step in runs)
    script = read(WINDOWS / "run-installer.ps1")
    assert "WaitForExit($TimeoutMinutes * 60 * 1000)" in script
    assert "taskkill" in script
    assert script.index("finally") < script.index("Get-Content $scriptLog")  # The logs show on failure too.


def test_the_manual_installer_job_installs_on_a_machine_without_python_and_then_upgrades():
    job_text = "\n".join(step_text(step) for step in workflow()["jobs"]["windows-installer-run"]["steps"])
    first = steps_text("windows-installer-run", "Run the installer (silently")
    # The step removes Python from the PATH (hostedtoolcache) and from the registry (PythonCore), before the installer.
    assert "hostedtoolcache" in first and "PythonCore" in first
    assert first.index("PythonCore") < first.index("run-installer.ps1 -Label first")
    assert "check-installed.ps1 -ExpectBundledPython" in job_text
    upgraded = steps_text("windows-installer-run", "Check the upgraded installation")
    # An upgrade finds Python already installed, so it does not expect the bundled one ...
    assert "-ExpectBundledPython" not in upgraded
    # ... it keeps the Python environment of the first installation instead of making another one ...
    assert "'recreating it'" in upgraded
    assert upgraded.index("'recreating it'") < upgraded.index("check-installed.ps1")
    # ... and the reminders that were on are on again.
    assert "check-installed.ps1 -ExpectAutostart" in upgraded


def test_the_upgrade_is_tested_with_the_users_data_and_with_the_reminders_on():
    job = workflow()["jobs"]["windows-installer-run"]
    names = [step.get("name", "") for step in job["steps"]]
    prepare = steps_text("windows-installer-run", "Put something of the user's")
    # Both folders that hold the user's data, and the program's own way of turning the reminders on.
    assert "$env:APPDATA 'multazem'" in prepare and "$env:LOCALAPPDATA 'multazem'" in prepare
    assert "service_install()" in prepare
    assert names.index(next(n for n in names if n.startswith("Put something"))) < names.index(
        next(n for n in names if n.startswith("Run the installer again"))
    )
    upgraded = steps_text("windows-installer-run", "Check the upgraded installation")
    assert upgraded.count("keep-me.txt") == 1 and "removed the user's data" in upgraded


def test_the_uninstaller_is_run_last_and_must_leave_nothing_signed_in_or_running():
    job = workflow()["jobs"]["windows-installer-run"]
    names = [step.get("name", "") for step in job["steps"]]
    uninstall = steps_text("windows-installer-run", "Uninstall")
    assert "unins000.exe" in uninstall and "/VERYSILENT" in uninstall
    for needed in (
        "Software\\Microsoft\\Windows\\CurrentVersion\\Run",
        "AppUserModelId\\com.github.multazem",
        "multazem\\s+--headless",
        "keep-me.txt",
    ):
        assert needed in uninstall, needed
    # After the scans, which need the installation, and before the report is uploaded.
    assert (
        names.index(next(n for n in names if n.startswith("Where do the Visual C++")))
        < names.index(next(n for n in names if n.startswith("Uninstall")))
        < len(names) - 1
    )


def test_a_failing_native_command_is_never_the_exit_code_of_a_step_that_otherwise_passed():
    """Keeps taskkill's exit code from becoming the exit code of the step.

    Actions ends a pwsh step with the exit code of the last native command: taskkill fails when part of the process
    tree is already gone. That is a result here, not a failure.
    """
    launch = steps_text("windows-full-install", "Launch the application")
    assert "$global:LASTEXITCODE = 0" in launch.split('cmd /c "taskkill')[1].split("\n")[0]
    checker = read(WINDOWS / "check-installed.ps1")
    assert "$global:LASTEXITCODE = 0" in checker.split('cmd /c "taskkill')[1].split("\n")[0]


def test_the_dll_scans_of_the_installed_program_fail_when_something_would_come_from_the_machine():
    scan = steps_text("windows-installer-run", "Which DLLs does the installed program need")
    # The script runs with the installed program's own python, in isolated mode, and nothing is allowed to be missing.
    assert "dlls.py scan --app $app --strict" in scan and "-I " in scan
    assert "--allow" not in scan
    # The report goes to the job summary and to a warning, and the full report is kept as JSON.
    assert "--github" in scan and "--json" in scan
    loaded = steps_text("windows-installer-run", "Where do the Visual C++ runtime DLLs")
    assert "dlls.py loaded --app $app --strict" in loaded
    job = workflow()["jobs"]["windows-installer-run"]
    for step in (scan, loaded):
        # The step runs even when an earlier step failed, so that its result is always reported.
        assert "!cancelled()" in step
        assert "throw" in step  # A failed check fails the step.
    uploads = [step for step in job["steps"] if "upload-artifact" in step.get("uses", "")]
    assert uploads[-1]["with"]["name"] == "dll-scan"
    assert uploads[-1]["with"]["path"] == "${{ runner.temp }}/dll-scan.json"
    names = [step.get("name", "") for step in job["steps"]]
    assert (
        names.index("Check the upgraded installation (the reminders that were on are on again)")
        < names.index("Which DLLs does the installed program need from the machine? (import tables)")
        < names.index("Where do the Visual C++ runtime DLLs of the running program come from?")
    )


def test_the_full_install_job_checks_the_shortcut_the_reminders_and_the_uninstall_script():
    job = workflow()["jobs"]["windows-full-install"]
    names = [step.get("name", "") for step in job["steps"]]
    install = steps_text("windows-full-install", "Install everything")
    assert "-PythonVersion 3.14" in install and "-Autostart" in install
    ordered = [
        "Install everything",
        "The Start menu entry points at something that exists",
        "The reminders are on",
        "Test suite",
        "Launch the application",
        "Remove it again with the uninstall script",
    ]
    positions = [next(i for i, name in enumerate(names) if name.startswith(prefix)) for prefix in ordered]
    assert positions == sorted(positions)
    assert "'-m', 'multazem'" in steps_text("windows-full-install", "Launch the application")
    removal = steps_text("windows-full-install", "Remove it again")
    assert "Multazem.lnk" in removal and "multazem\\s+--headless" in removal
