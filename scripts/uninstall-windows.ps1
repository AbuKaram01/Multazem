# SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
# SPDX-License-Identifier: MIT
#
# uninstall-windows.ps1 - removes what scripts\install-windows.ps1 created.

<#
.SYNOPSIS
    Removes what scripts\install-windows.ps1 created.
.DESCRIPTION
    Stops the background reminders and removes their sign-in entry first, because a running program keeps its files in
    use. Your settings and your own regions are kept unless you ask for them to be deleted.
.PARAMETER StopOnly
    Only stop the background reminders (what an upgrade needs before it replaces the program files); remove nothing
    and leave the sign-in entry alone.
.PARAMETER RemoveGtk
    Also delete the GTK runtime a download put in %LOCALAPPDATA%\multazem\gtk.
.PARAMETER RemoveData
    Also delete the settings, the saved regions and the log. Cannot be undone.
.PARAMETER Force
    Do not ask for confirmation before -RemoveData deletes anything.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\uninstall-windows.ps1 -RemoveGtk -RemoveData
#>
[CmdletBinding()]
param(
    [switch]$StopOnly,
    [switch]$RemoveGtk,
    [switch]$RemoveData,
    [switch]$Force
)

Set-StrictMode -Version 2.0

# This script is for Windows only; say so clearly instead of failing on a missing %LOCALAPPDATA%.
if ($env:OS -ne 'Windows_NT') {
    Write-Host 'ERR This script is for Windows. On Linux use your package manager.' -ForegroundColor Red
    exit 1
}
$ErrorActionPreference = 'Stop'

$AppId       = 'com.github.multazem'
$RunKey      = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DataRoot    = Join-Path $env:LOCALAPPDATA 'multazem'
$ConfigRoot  = Join-Path $env:APPDATA 'multazem'

function Info($Text) { Write-Host "==> $Text" -ForegroundColor Cyan }
function Remove-IfPresent([string]$Path) {
    if (Test-Path $Path) { Remove-Item $Path -Recurse -Force; Info "Removed $Path" }
}

# Whether the process with this id is a Multazem background process: its command line says so. A number that is left
# in background.pid after a crash may belong to some other program by now, and that one must never be stopped.
function Test-BackgroundProcess([int]$ProcessId) {
    $process = Get-CimInstance -ClassName Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    return [bool]($process -and ([string]$process.CommandLine) -match 'multazem\s+--headless')
}

# The background process records its id in background.pid while it runs (see services\windows_service.py); ending it
# lets the files of the environment be deleted.
function Stop-BackgroundProcess {
    $pidFile = Join-Path $DataRoot 'background.pid'
    if (-not (Test-Path $pidFile)) { return }
    $text = (Get-Content -LiteralPath $pidFile -TotalCount 1 -ErrorAction SilentlyContinue)
    $number = 0
    if (-not ($text -and [int]::TryParse(([string]$text).Trim(), [ref]$number) -and $number -gt 0)) { return }
    if (-not (Test-BackgroundProcess $number)) { return }
    Info "Stopping the background reminders (process $number)..."
    Stop-Process -Id $number -Force -ErrorAction SilentlyContinue
    [void](Get-Process -Id $number -ErrorAction SilentlyContinue | ForEach-Object { $_.WaitForExit(5000) })
}

if ($RemoveData -and -not $Force) {
    $answer = Read-Host 'This deletes your settings and saved regions. Type YES to continue'
    if ($answer -ne 'YES') { Write-Host 'Nothing was deleted.'; exit 1 }
}

Stop-BackgroundProcess
if ($StopOnly) { exit 0 }
if (Get-ItemProperty -Path $RunKey -Name 'Multazem' -ErrorAction SilentlyContinue) {
    Remove-ItemProperty -Path $RunKey -Name 'Multazem'
    Info 'Removed the sign-in entry of the reminders.'
}
Remove-IfPresent (Join-Path ([Environment]::GetFolderPath('Programs')) 'Multazem.lnk')
Remove-IfPresent (Join-Path $ProjectRoot '.venv')
# The GTK runtime the installer carried (the note beside it says it was prepared by the build, not by you).
$carriedGtk = Join-Path $ProjectRoot 'gtk'
if (Test-Path (Join-Path $carriedGtk 'gvsbuild-release.txt')) { Remove-IfPresent $carriedGtk }
Remove-IfPresent "HKCU:\Software\Classes\AppUserModelId\$AppId"
[Environment]::SetEnvironmentVariable('MULTAZEM_GTK_DIR', $null, 'User')

if ($RemoveGtk) { Remove-IfPresent (Join-Path $DataRoot 'gtk') }
if ($RemoveData) {
    Remove-IfPresent $ConfigRoot
    Get-ChildItem $DataRoot -Force -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -ne 'gtk' -or $RemoveGtk } |
        ForEach-Object { Remove-IfPresent $_.FullName }
    if ((Test-Path $DataRoot) -and -not (Get-ChildItem $DataRoot -Force)) { Remove-Item $DataRoot -Force }
}

Write-Host 'Done.'
if (-not $RemoveData) { Write-Host "Your data is still in $DataRoot and $ConfigRoot (use -RemoveData to delete it)." }
