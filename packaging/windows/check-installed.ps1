# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT
#
# check-installed.ps1 - checks an installation made by multazem-<version>-windows-setup.exe, for the manual CI job
# "windows-installer-run" and for a trial installation in a virtual machine.

<#
.SYNOPSIS
    Checks that an installation made by the Multazem installer looks the way a user's machine should.
.DESCRIPTION
    Stops with an error at the first thing that is wrong. It checks that

      * the GTK runtime is the one the installer carried, and that no second copy was downloaded;
      * the Python environment exists and its libraries came from the wheelhouse inside the installer (nothing
        downloaded);
      * GTK and libadwaita load from that folder without being told where it is;
      * the libraries of the program import, with and without a console, and the time zone of Cairo is known (Windows
        has no time zone database of its own, so tzdata has to be there);
      * the application stays up for a few seconds, the way the Start menu entry starts it;
      * the background reminders can be turned on and off the way the Autostart button does it (a Run value, and a
        process that holds the lock) and leave nothing behind.
.PARAMETER App
    The installation folder. The default is where the installer puts it for the current user.
.PARAMETER SecondsToRun
    How long the application has to stay up.
.PARAMETER ExpectBundledPython
    Also check that Python itself came from the python.org installer inside the installer. Use it where no Python
    is installed yet.
.PARAMETER ExpectAutostart
    The installation was made with the "autostart" task (or an earlier one had it): the reminders must already be on.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File packaging\windows\check-installed.ps1 -ExpectBundledPython
#>
param(
    [string]$App = (Join-Path $env:LOCALAPPDATA 'Programs\Multazem'),
    [int]$SecondsToRun = 15,
    [switch]$ExpectBundledPython,
    [switch]$ExpectAutostart
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

function Ok([string]$Text) { Write-Host "OK  $Text" -ForegroundColor Green }

# Writes a Python program into the temp folder and returns its path.
function New-Probe([string]$Name, [string]$Source) {
    $path = Join-Path ([IO.Path]::GetTempPath()) "multazem-check-$Name.py"
    Set-Content -LiteralPath $path -Encoding UTF8 -Value $Source
    return $path
}

# Runs a Python program with the interpreter of the installed environment, waits for it, and returns what it printed.
# Python's own exit code decides: a probe that raises fails the check, with what it said.
function Invoke-Probe([string]$Probe, [string]$Failure) {
    $saved = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = & $script:Python $Probe 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $saved
    if ($code -ne 0) { throw "$Failure (exit code $code):`n$($output -join "`n")" }
    return ($output -join "`n")
}

# 1. The runtime the installer carried is beside the application.
$gtk = Join-Path $App 'gtk'
$neededInGtk = 'bin',
               'lib\girepository-1.0\Gtk-4.0.typelib',
               'lib\girepository-1.0\Adw-1.typelib',
               'wheels',
               'gvsbuild-release.txt'
foreach ($needed in $neededInGtk) {
    if (-not (Test-Path (Join-Path $gtk $needed))) { throw "The installer did not put $needed in $gtk." }
}
Get-Content (Join-Path $gtk 'gvsbuild-release.txt') | ForEach-Object { Write-Host "    $_" }
Ok "GTK is in $gtk"

# 1b. The build tools of the GTK release were left out (the installer would otherwise carry about a gigabyte more, and
# the C++ libraries among them are the only ones that need msvcp140.dll).
foreach ($unwanted in 'include', 'bin\protoc.exe', 'bin\gtkmm-vc143-4.0-0.dll') {
    if (Test-Path (Join-Path $gtk $unwanted)) { throw "$unwanted is in $gtk; the build left out too little." }
}
if (@(Get-ChildItem $gtk -Recurse -Filter '*.pdb' -ErrorAction SilentlyContinue).Count -gt 0) {
    throw "There are debug symbols (*.pdb) in $gtk."
}
Ok 'the GTK runtime carries no debug symbols or build tools'

# 2. Nothing was downloaded to the place where the install script puts a runtime of its own.
$downloaded = Join-Path $env:LOCALAPPDATA 'multazem\gtk'
if (Test-Path $downloaded) { throw "GTK was downloaded into $downloaded although the installer carries it." }
Ok 'no second copy of GTK was downloaded'

# 3. The install script ran to the end.
$script:Python = Join-Path $App '.venv\Scripts\python.exe'
if (-not (Test-Path $script:Python)) {
    throw "The Python environment was not created in $App\.venv: the install script did not finish."
}
Ok 'the Python environment exists'

# 3b. What the install script did about Python and its libraries, from the log it keeps. The installer carries the
# libraries (a wheelhouse), so none may have been downloaded, and Python itself must not have needed winget.
$wheelhouse = Join-Path $App 'wheelhouse'
foreach ($library in 'adhanpy', 'tzdata', 'setuptools') {
    if (-not @(Get-ChildItem $wheelhouse -Filter "$library-*.whl" -ErrorAction SilentlyContinue)) {
        throw "The installer did not put the Python libraries (a wheelhouse with $library) in $wheelhouse."
    }
}
Ok "the Python libraries are in $wheelhouse"
$installLog = Join-Path $env:LOCALAPPDATA 'multazem\install.log'
if (-not (Test-Path $installLog)) { throw "The install script left no log at $installLog." }
$logText = Get-Content $installLog -Raw
if ($logText -notmatch 'Python libraries installed from the wheelhouse') {
    throw "The libraries were not installed from the wheelhouse; see $installLog."
}
foreach ($forbidden in 'downloading them instead', 'Installing Python \S+ with winget') {
    if ($logText -match $forbidden) {
        throw ("The installation used the internet where it should not have ('$forbidden'); see $installLog.")
    }
}
Ok 'the libraries were installed from the wheelhouse, with nothing downloaded'
if ($ExpectBundledPython) {
    if ($logText -notmatch 'installer that came with Multazem') {
        throw "Python was not installed from the installer that came with Multazem; see $installLog."
    }
    $venvHome = Get-Content (Join-Path $App '.venv\pyvenv.cfg') |
        Where-Object { $_ -match '^home\s*=' } |
        Select-Object -First 1
    if (-not $venvHome -or $venvHome -notmatch 'Programs\\Python\\Python\d+') {
        throw "The environment was not made from the Python that the installer installed ($venvHome)."
    }
    Ok "Python came from the installer inside Multazem ($($venvHome.Trim()))"
}

# 4. GTK loads from that folder, with nothing telling the application where it is.
Remove-Item Env:MULTAZEM_GTK_DIR -ErrorAction SilentlyContinue
$gtkProbe = New-Probe 'gtk' @'
import sys
from pathlib import Path

import multazem.app  # prepares the runtime before GTK is imported
from multazem import winsupport
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

found = winsupport.find_gtk_runtime()
print("runtime found:", found)
print(
    "GTK %d.%d, libadwaita %d.%d"
    % (Gtk.get_major_version(), Gtk.get_minor_version(), Adw.get_major_version(), Adw.get_minor_version())
)
beside = Path(sys.prefix).parent / "gtk"
assert found is not None and found.resolve() == beside.resolve(), (
    f"expected the runtime beside the application: {beside}"
)
'@
Write-Host (Invoke-Probe $gtkProbe "GTK did not load from the installer's folder")
Ok 'GTK and libadwaita load from the installer''s folder'

# 4b. The libraries of the program load in the installed environment, from a console program (python.exe) and from one
# that has no console, as the Start menu entry runs it (pythonw.exe, where a program started without a window of its own
# behaves differently), and the time zone that the default region needs is known.
$libraryProbeSource = @'
import sys
from zoneinfo import ZoneInfo

import multazem.app  # Prepares the runtime first, as the program does.
import adhanpy
import cairo
import gi

for zone in ("Africa/Cairo", "Asia/Riyadh"):
    ZoneInfo(zone)  # Raises when Windows has no time zone data and the tzdata package is not installed.
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    handle.write("pycairo %s, PyGObject %s, time zone data found" % (cairo.version, gi.__version__))
'@

# Runs the probe with one interpreter of the installed environment and returns what it wrote.
function Get-LibraryAnswer([string]$Interpreter, [string]$ProbeScript) {
    $answerFile = Join-Path ([IO.Path]::GetTempPath()) "multazem-libraries-$Interpreter.txt"
    Remove-Item -LiteralPath $answerFile -ErrorAction SilentlyContinue
    $arguments = "`"$ProbeScript`"", "`"$answerFile`""
    Start-Process -FilePath (Join-Path $App ".venv\Scripts\$Interpreter") -ArgumentList $arguments `
                  -WorkingDirectory $App -WindowStyle Hidden
    # pythonw.exe hands over to the real interpreter and may end before it does: wait for the answer itself.
    $deadline = (Get-Date).AddSeconds(120)
    while (-not (Test-Path -LiteralPath $answerFile) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-Path -LiteralPath $answerFile)) {
        throw "$Interpreter could not import the libraries within two minutes."
    }
    Start-Sleep -Milliseconds 300
    return (Get-Content -LiteralPath $answerFile -Raw).Trim()
}

$libraryProbe = New-Probe 'libraries' $libraryProbeSource
foreach ($interpreter in 'python.exe', 'pythonw.exe') {
    Write-Host "    ${interpreter}: $(Get-LibraryAnswer $interpreter $libraryProbe)"
}
Ok 'the libraries load (with and without a console) and Windows has the time zone data'

# 5. The application starts and keeps running.
$pythonw = Join-Path $App '.venv\Scripts\pythonw.exe'
$process = Start-Process -FilePath $pythonw -ArgumentList '-m', 'multazem' -WorkingDirectory $App -PassThru
Start-Sleep -Seconds $SecondsToRun
$exited = $process.HasExited
# pythonw starts the real interpreter as a child, so the whole tree has to be stopped. taskkill fails when part of
# that tree is already gone, and a script that ends right after it would exit with taskkill's code: so it is run by
# cmd and its code forgotten.
if (-not $exited) { cmd /c "taskkill /PID $($process.Id) /T /F >nul 2>&1"; $global:LASTEXITCODE = 0 }
$log = Join-Path $env:LOCALAPPDATA 'multazem\multazem.log'
if (Test-Path $log) { Write-Host '--- multazem.log'; Get-Content $log }
if ($exited) { throw "The application exited early with code $($process.ExitCode)." }
Ok "the application was still running after $SecondsToRun seconds"

# 6. The background reminders. The probe does what the Autostart button does and checks each step from the outside:
# the Run value, the lock that the background process holds, and the process id it records.
$serviceProbe = New-Probe 'service' @'
import sys
import time

from multazem.services import windows_service as service
from multazem.services.paths import local_data_dir

expect_on = sys.argv[1] == "on"
pid_file = local_data_dir() / "background.pid"
assert service.service_is_enabled() == expect_on, "the Run value is not what the installation should have left"
assert service.service_is_active() == expect_on, "the background process is not what the installation should have left"

if not expect_on:
    ok, text = service.service_install()
    print(text)
    assert ok, "the background reminders could not be turned on"
assert service.service_is_enabled() and service.service_is_active()
# The process takes its lock first and writes its process id a moment later.
deadline = time.monotonic() + 10
while not pid_file.exists() and time.monotonic() < deadline:
    time.sleep(0.2)
assert pid_file.exists(), "the background process left no process id"
assert pid_file.read_text(encoding="ascii").strip().isdigit(), "the process id file does not hold a number"
print("reminders on, process", pid_file.read_text(encoding="ascii").strip())

ok, text = service.service_uninstall()
print(text)
assert ok, "the background reminders could not be turned off"
deadline = time.monotonic() + 10
while service.service_is_active() and time.monotonic() < deadline:
    time.sleep(0.2)
assert not service.service_is_enabled() and not service.service_is_active(), "turning them off left something running"
assert not pid_file.exists(), "the process id file was left behind"
print("reminders off")
'@
$state = if ($ExpectAutostart) { 'on' } else { 'off' }
$saved = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$serviceOutput = & $script:Python $serviceProbe $state 2>&1
$serviceExit = $LASTEXITCODE
$ErrorActionPreference = $saved
Write-Host ($serviceOutput -join "`n")
if ($serviceExit -ne 0) { throw "The background reminders did not behave (exit code $serviceExit)." }
if ($ExpectAutostart) {
    Ok 'the installer left the reminders on, and they turn off cleanly'
} else {
    Ok 'the reminders turn on and off cleanly'
}
