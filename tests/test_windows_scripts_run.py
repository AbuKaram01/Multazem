# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT

"""The PowerShell scripts of the Windows installation that can be run on any system, run for real.

The uninstall script's way of stopping the background reminders is the one part of an upgrade that must never hurt:
a process id that a crash left in a file may belong to another program by now. The probes that the installation check
runs inside the installed program are Python programs, so they are compiled here and the ones that can run, run.
"""

import os
import re
import subprocess
import sys
import time

import pytest

from multazem.services import windows_service

from packaging_support import ROOT, WINDOWS, needs_pwsh, read

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the stand-ins are for a system without Windows")

UNINSTALL = ROOT / "scripts" / "uninstall-windows.ps1"
BACKGROUND_COMMAND_LINE = (
    '"C:\\Users\\me\\AppData\\Local\\Programs\\Multazem\\.venv\\Scripts\\pythonw.exe" -m multazem --headless'
)

WRAPPER = """\\
# Windows' process list is not here: the stand-in answers with the command line that the test says the process has.
function Get-CimInstance {{
    [CmdletBinding()]
    param($ClassName, $Filter)
    Set-Content -LiteralPath '{filter_log}' -Value $Filter
    if ($env:FAKE_COMMAND_LINE) {{ [pscustomobject]@{{ CommandLine = $env:FAKE_COMMAND_LINE }} }}
}}
& '{script}' {arguments}
exit $LASTEXITCODE
"""


def run_uninstall(tmp_path, *arguments, command_line=None, pid_text=None):
    """Runs the uninstall script as if on Windows.

    Returns:
        ``(result, the filter the script asked the process list with)``.
    """
    data = tmp_path / "local" / "multazem"
    data.mkdir(parents=True, exist_ok=True)
    if pid_text is not None:
        (data / windows_service.PRESENCE_PID_NAME).write_text(pid_text, encoding="ascii")
    filter_log = tmp_path / "filter.txt"
    wrapper = tmp_path / "wrapper.ps1"
    wrapper.write_text(
        WRAPPER.format(filter_log=filter_log, script=UNINSTALL, arguments=" ".join(arguments)), encoding="utf-8"
    )
    environment = {**os.environ, "OS": "Windows_NT", "LOCALAPPDATA": str(tmp_path / "local")}
    environment["APPDATA"] = str(tmp_path / "roaming")
    environment["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] = "1"
    if command_line is not None:
        environment["FAKE_COMMAND_LINE"] = command_line
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(wrapper)], capture_output=True, text=True, check=False, env=environment
    )
    asked = filter_log.read_text(encoding="utf-8").strip() if filter_log.exists() else ""
    return result, asked


@pytest.fixture
def stranger():
    """A running process that belongs to nobody the scripts know about."""
    process = subprocess.Popen(["sleep", "60"])
    yield process
    if process.poll() is None:
        process.kill()
    process.wait()


@needs_pwsh
def test_the_background_process_of_multazem_is_stopped_before_an_upgrade_replaces_its_files(tmp_path, stranger):
    result, asked = run_uninstall(
        tmp_path, "-StopOnly", command_line=BACKGROUND_COMMAND_LINE, pid_text=f"{stranger.pid}\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert asked == f"ProcessId = {stranger.pid}"
    assert stranger.wait(timeout=20) != 0  # Ended by the script, not by itself.
    assert "Stopping the background reminders" in result.stdout


@needs_pwsh
@pytest.mark.parametrize(
    "command_line",
    ['"C:\\Windows\\notepad.exe" notes.txt', '"C:\\Python\\python.exe" -m multazem', ""],
    ids=["another program", "the window of Multazem, not the reminders", "a process that is gone"],
)
def test_a_process_id_left_behind_by_a_crash_never_stops_a_process_that_is_not_the_background_process(
    tmp_path, stranger, command_line
):
    result, _asked = run_uninstall(tmp_path, "-StopOnly", command_line=command_line, pid_text=f"{stranger.pid}\n")
    assert result.returncode == 0, result.stdout + result.stderr
    time.sleep(0.5)
    assert stranger.poll() is None, "the script stopped a process that is not the background process"
    assert "Stopping the background reminders" not in result.stdout


@needs_pwsh
@pytest.mark.parametrize("pid_text", [None, "", "not a number", "0", "-5", "12 34"], ids=repr)
def test_without_a_usable_process_id_there_is_nothing_to_stop_and_nothing_fails(tmp_path, pid_text):
    result, asked = run_uninstall(tmp_path, "-StopOnly", command_line=BACKGROUND_COMMAND_LINE, pid_text=pid_text)
    assert result.returncode == 0, result.stdout + result.stderr
    assert asked == ""  # The process list was never asked about anything.


@needs_pwsh
@pytest.mark.parametrize("name", ["install-windows.ps1", "uninstall-windows.ps1"])
def test_the_windows_scripts_say_so_when_they_are_run_on_another_system(name):
    result = subprocess.run(
        ["pwsh", "-NoProfile", "-File", str(ROOT / "scripts" / name)],
        capture_output=True,
        text=True,
        check=False,
        env={key: value for key, value in os.environ.items() if key != "OS"}
        | {"DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "1"},
    )
    assert result.returncode == 1
    assert "This script is for Windows" in result.stdout + result.stderr


# --- The probes that the installation check runs inside the installed program ---


def probes(script: str) -> dict[str, str]:
    """Returns the Python programs that a PowerShell script holds in here-strings, by the name they are given."""
    found = {}
    for match in re.finditer(r"(?:New-Probe '(\w+)'|\$(\w+) =) @'\n(.*?)\n'@", script, re.DOTALL):
        found[match.group(1) or match.group(2)] = match.group(3)
    return found


def test_the_installation_check_holds_three_python_probes_and_the_library_probe_is_one_of_them():
    assert set(probes(read(WINDOWS / "check-installed.ps1"))) == {"gtk", "libraryProbeSource", "service"}


@pytest.mark.parametrize("name", ["gtk", "libraryProbeSource", "service"])
def test_every_python_probe_of_the_installation_check_is_valid_python(name):
    compile(probes(read(WINDOWS / "check-installed.ps1"))[name], f"<{name} probe>", "exec")


def test_the_service_probe_uses_names_that_the_service_module_has_and_the_file_that_it_writes():
    source = probes(read(WINDOWS / "check-installed.ps1"))["service"]
    for name in re.findall(r"service\.(\w+)\(", source):
        assert callable(getattr(windows_service, name)), name
    assert windows_service.PRESENCE_PID_NAME in source
    from multazem.services import paths

    assert callable(paths.local_data_dir) and "local_data_dir" in source


def test_the_library_probe_runs_and_writes_its_answer(tmp_path):
    """Runs the probe with a stand-in for pycairo, which comes from the GTK runtime's wheels on Windows only."""
    pytest.importorskip("gi")
    (tmp_path / "stand_in").mkdir()
    (tmp_path / "stand_in" / "cairo.py").write_text('version = "stand-in"\n', encoding="utf-8")
    probe = tmp_path / "probe.py"
    probe.write_text(probes(read(WINDOWS / "check-installed.ps1"))["libraryProbeSource"], encoding="utf-8")
    answer = tmp_path / "answer.txt"
    result = subprocess.run(
        [sys.executable, str(probe), str(answer)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(tmp_path / "stand_in"), str(ROOT / "src")])},
    )
    assert result.returncode == 0, result.stderr
    text = answer.read_text(encoding="utf-8")
    assert "pycairo stand-in" in text
    assert "PyGObject" in text
    assert "time zone data found" in text
