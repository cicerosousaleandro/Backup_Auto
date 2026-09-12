#define MyAppName "Backup_Auto"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Backup_Auto"
#define MyAppExeName "Backup_Auto.exe"

[Setup]
AppId={{7F3B0F6A-2C9B-4C4F-9D2B-8A8D8F1C6E11}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={commonappdata}\Backup_Auto
DisableProgramGroupPage=yes
DisableDirPage=yes
OutputDir=output
OutputBaseFilename=Backup_Auto_Setup
SetupIconFile=..\images.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible

[Dirs]
Name: "{app}"; Permissions: users-modify
Name: "{app}\logs"; Permissions: users-modify

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function ConfigureBackupAuto(): Boolean;
var
  ResultCode: Integer;
  ExePath: String;
begin
  Result := False;

  ExePath := ExpandConstant(
    '{app}\{#MyAppExeName}'
  );

  WizardForm.StatusLabel.Caption :=
    'Configurando os Backup Sets do computador...';

  if not FileExists(ExePath) then
  begin
    MsgBox(
      'O Backup_Auto.exe não foi encontrado após a instalação.' +
      Chr(13) + Chr(10) + Chr(13) + Chr(10) +
      'Arquivo esperado:' +
      Chr(13) + Chr(10) +
      ExePath,
      mbError,
      MB_OK
    );

    Exit;
  end;

  if ExecAsOriginalUser(
    ExePath,
    '--configure',
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    if ResultCode = 0 then
    begin
      Result := True;
      Exit;
    end;

    MsgBox(
      'Não foi possível configurar automaticamente os Backup Sets do CloudBackupPRO.' +
      Chr(13) + Chr(10) + Chr(13) + Chr(10) +
      'Código retornado: ' + IntToStr(ResultCode) +
      Chr(13) + Chr(10) + Chr(13) + Chr(10) +
      'Verifique se o CloudBackupPRO está instalado e se existe um Backup Set configurado.',
      mbError,
      MB_OK
    );
  end
  else
  begin
    MsgBox(
      'Não foi possível iniciar a configuração automática do Backup_Auto.',
      mbError,
      MB_OK
    );
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not ConfigureBackupAuto() then
    begin
      MsgBox(
        'A instalação do Backup_Auto foi concluída, mas a configuração automática não foi concluída.' +
        Chr(13) + Chr(10) + Chr(13) + Chr(10) +
        'O programa foi instalado em:' +
        Chr(13) + Chr(10) +
        ExpandConstant('{app}'),
        mbError,
        MB_OK
      );
    end;
  end;
end;

procedure CurUninstallStepChanged(
  CurUninstallStep: TUninstallStep
);
begin
  if CurUninstallStep = usUninstall then
  begin
    RegDeleteValue(
      HKCU,
      'Software\Microsoft\Windows\CurrentVersion\Run',
      'Backup_Auto'
    );
  end;
end;