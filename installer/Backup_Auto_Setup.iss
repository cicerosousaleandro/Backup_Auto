#define MyAppName "Backup_Auto"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "AM3 Soluções"
#define MyAppExeName "Backup_Auto.exe"

[Setup]
AppId={{8F4B6B6D-8E35-4B5F-9F7B-BA9C7A5D9A11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Backup_Auto
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=Backup_Auto_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\images.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\Backup_Auto.exe"; DestDir: "{app}"; Flags: ignoreversion

[UninstallDelete]
Type: files; Name: "{userappdata}\Microsoft\Windows\Start Menu\Programs\Startup\Backup_Auto_Start.vbs"
Type: files; Name: "{userappdata}\Microsoft\Windows\Start Menu\Programs\Startup\Backup_Auto.lnk"
Type: files; Name: "{userappdata}\Microsoft\Windows\Start Menu\Programs\Startup\Backup_Auto_Start.cmd"
Type: filesandordirs; Name: "{app}\logs"

[Code]

procedure CreateStartupScript;
var
  StartupPath: string;
  ScriptPath: string;
  ScriptContent: string;
begin
  StartupPath := ExpandConstant('{userappdata}\Microsoft\Windows\Start Menu\Programs\Startup');
  ScriptPath := StartupPath + '\Backup_Auto_Start.vbs';

  ForceDirectories(StartupPath);

  ScriptContent :=
    'Set shell = CreateObject("WScript.Shell")' + #13#10 +
    'shell.Run Chr(34) & "' + ExpandConstant('{app}') + '\Backup_Auto.exe" & Chr(34), 0, False' + #13#10 +
    'Set shell = Nothing' + #13#10;

  SaveStringToFile(
    ScriptPath,
    ScriptContent,
    False
  );
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CreateStartupScript;
  end;
end;