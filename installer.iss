; Dizflow installer (Inno Setup 6).  Built by build.py -> dist\installer\Dizflow-Setup-<version>.exe
#define AppName "Dizflow"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{8C2F4A1E-5D7B-4E3A-9B61-D17F10A00001}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=Dizflow-Setup-{#AppVersion}
SetupIconFile=build\dizflow.ico
UninstallDisplayIcon={app}\Dizflow.exe
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=8
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "autostart"; Description: "Start Dizflow when I sign in to Windows (recommended)"; GroupDescription: "Startup:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "dist\Dizflow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Dizflow.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\Dizflow.exe"; Tasks: desktopicon

[Registry]
; Start with Windows (in the tray, window hidden). Dizflow keeps this in sync with its own Settings toggle.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Dizflow"; \
    ValueData: """{app}\Dizflow.exe"" --minimized"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Dizflow.exe"; Description: "Launch Dizflow now"; Flags: nowait postinstall skipifsilent
; Automatic update (silent install started by Dizflow itself): start the new version straight away.
Filename: "{app}\Dizflow.exe"; Flags: nowait; Check: IsAutoUpdate

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/im Dizflow.exe /f"; Flags: runhidden; RunOnceId: "StopDizflow"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function IsAutoUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATE|0}') = '1';
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
  Path: String;
begin
  if CurStep = ssInstall then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/im Dizflow.exe /f', '', SW_HIDE, ewWaitUntilTerminated, Code);
  { On an automatic update keep whatever the user chose in Dizflow's own Settings. }
  if (CurStep = ssPostInstall) and not IsAutoUpdate then
  begin
    { Tell the app which choice was made so its Settings toggle matches the installer. }
    Path := ExpandConstant('{userappdata}\Dizflow\installer-autostart.txt');
    ForceDirectories(ExtractFileDir(Path));
    if WizardIsTaskSelected('autostart') then
      SaveStringToFile(Path, '1', False)
    else
      SaveStringToFile(Path, '0', False);
  end;
end;
