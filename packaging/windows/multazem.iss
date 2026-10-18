; SPDX-FileCopyrightText: 2026 AbuKaram01 <abukaram01@proton.me>
; SPDX-License-Identifier: MIT
;
; Inno Setup script for the Windows installer. Build it with packaging\build-windows.ps1.
;
; The installer ships Multazem's own files, the GTK 4 + libadwaita runtime, Python's installer and the Python libraries
; (a "wheelhouse": adhanpy, tzdata ...) when packaging\build-windows.ps1 prepared them. After copying them it runs
; scripts\install-windows.ps1, which installs Python (when it is missing), creates the Python environment and installs
; the libraries from the wheelhouse, and downloads only what the installer does not carry.
; Everything is per user: no administrator rights are required.

#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
#define AppName "Multazem"
#define AppId "com.github.multazem"

[Setup]
AppId={{2BCDFBC6-CEDD-48CE-A941-8E46E1B0ECDB}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=AbuKaram01
AppPublisherURL=https://github.com/AbuKaram01/Multazem
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
SetupIconFile=..\..\data\windows\multazem.ico
UninstallDisplayIcon={app}\data\windows\multazem.ico
OutputDir=..\dist
OutputBaseFilename=multazem-{#AppVersion}-windows-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Keep the prayer reminders running in the background and start them when I sign in to Windows"; Flags: unchecked
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\..\src\*"; DestDir: "{app}\src"; Excludes: "__pycache__,*.pyc,*.egg-info"; Flags: recursesubdirs ignoreversion
Source: "..\..\data\*"; DestDir: "{app}\data"; Flags: recursesubdirs ignoreversion
Source: "..\..\scripts\install-windows.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\scripts\gtk-portable.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\scripts\python-bundle.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\scripts\uninstall-windows.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

; The GTK 4 + libadwaita runtime that packaging\build-windows.ps1 prepared: installed beside the application, where
; the application finds it by itself, so that it does not have to be downloaded. The install script uses it when it is
; there and downloads one only when it is not.
#define GtkFolder SourcePath + "\..\gtk"
#if DirExists(GtkFolder)
Source: "{#GtkFolder}\*"; DestDir: "{app}\gtk"; Flags: recursesubdirs ignoreversion
#endif

; The python.org installer of the Python that the GTK runtime's wheels are for: the install script runs it, silently and
; for the current user, when that Python is missing, so that winget is not needed.
#define PythonFolder SourcePath + "\..\python"
#if DirExists(PythonFolder)
Source: "{#PythonFolder}\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion
#endif

; The Python libraries (wheels) that packaging\build-windows.ps1 prepared: the install script installs them without
; internet access.
#define WheelFolder SourcePath + "\..\wheelhouse"
#if DirExists(WheelFolder)
Source: "{#WheelFolder}\*"; DestDir: "{app}\wheelhouse"; Flags: recursesubdirs ignoreversion
#endif

[InstallDelete]
#if DirExists(GtkFolder)
; An upgrade starts from an empty runtime folder, so that no file of an older runtime stays beside the new DLLs.
Type: filesandordirs; Name: "{app}\gtk"
#endif
#if DirExists(PythonFolder)
Type: filesandordirs; Name: "{app}\python"
#endif
#if DirExists(WheelFolder)
Type: filesandordirs; Name: "{app}\wheelhouse"
#endif

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: "-m multazem"; WorkingDir: "{app}"; IconFilename: "{app}\data\windows\multazem.ico"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: "-m multazem"; WorkingDir: "{app}"; IconFilename: "{app}\data\windows\multazem.ico"; Tasks: desktopicon

[Registry]
; The application registers its notification identity here at run time; this makes the uninstaller remove it.
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\{#AppId}"; Flags: uninsdeletekey

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\src"
Type: filesandordirs; Name: "{app}\build"
Type: filesandordirs; Name: "{app}\gtk"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\wheelhouse"
; The GTK runtime that an install script run by hand downloaded. The settings, the saved regions and the log are never
; removed.
Type: filesandordirs; Name: "{localappdata}\multazem\gtk"

[Code]
// Runs the uninstall script of the installation that is already there (an upgrade) or being removed. -StopOnly ends
// the background reminders, which keep files of the Python environment in use; without it the script also removes
// their sign-in entry. Nothing happens when the script is not there (a first installation).
procedure RunUninstallScript(Options: String);
var
  ScriptPath: String;
  ResultCode: Integer;
begin
  ScriptPath := ExpandConstant('{app}\scripts\uninstall-windows.ps1');
  if not FileExists(ScriptPath) then
    Exit;
  Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '" ' + Options, '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

var
  RemindersWereOn: Boolean;

// Whether the reminders start at sign-in (the Run value that the program writes when Autostart is turned on).
function RemindersAreOn: Boolean;
begin
  Result := RegValueExists(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Multazem');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  // An upgrade replaces the Python environment, so the running background process has to go first; if the user had
  // the reminders on, they are started again after the installation.
  RemindersWereOn := RemindersAreOn;
  RunUninstallScript('-StopOnly');
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Parameters: String;
  ResultCode: Integer;
begin
  if CurStep <> ssPostInstall then
    Exit;
  Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\scripts\install-windows.ps1') + '" -NoShortcut -LogFile "' + ExpandConstant('{localappdata}\multazem\install.log') + '"';
  if WizardIsTaskSelected('autostart') or RemindersWereOn then
    Parameters := Parameters + ' -Autostart';
#if DirExists(GtkFolder) && DirExists(PythonFolder) && DirExists(WheelFolder)
  WizardForm.StatusLabel.Caption := 'Setting up Python and its libraries (everything is already in this installer; this takes a minute)...';
#elif DirExists(GtkFolder)
  WizardForm.StatusLabel.Caption := 'Setting up Python and the dependencies (GTK is already in this installer; what is not is downloaded)...';
#else
  WizardForm.StatusLabel.Caption := 'Setting up GTK, Python and the dependencies (a few hundred megabytes are downloaded)...';
#endif
  if (not Exec('powershell.exe', Parameters, ExpandConstant('{app}'), SW_SHOW, ewWaitUntilTerminated, ResultCode)) or (ResultCode <> 0) then
    MsgBox('Multazem was copied, but its components could not be set up.' + #13#10 + #13#10 +
           'What went wrong is written in ' + ExpandConstant('{localappdata}\multazem\install.log') + #13#10 + #13#10 +
           'Check your internet connection and run this again from a PowerShell window:' + #13#10 +
           'powershell -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\scripts\install-windows.ps1') + '"',
           mbError, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // The reminders are stopped and their sign-in entry removed before the files that they use are deleted.
  if CurUninstallStep = usUninstall then
    RunUninstallScript('-Force');
end;
