; Compile with Inno Setup 6.7.3. Private input paths arrive via /D values.
#ifndef AppVersion
  #error AppVersion required
#endif
#ifndef SourceDir
  #error SourceDir required
#endif
#ifndef OutputDir
  #error OutputDir required
#endif

[Setup]
AppId={{9BB91B13-A9B6-4484-B3E8-C71BC2D0088E}
AppName=BellalunAuto
AppVersion={#AppVersion}
AppPublisher=Bellalun QA
DefaultDirName={autopf}\BellalunAuto
DefaultGroupName=BellalunAuto
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=BellalunAuto-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ChangesEnvironment=yes
UninstallDisplayIcon={app}\BellalunAuto.exe
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면 바로 가기 만들기"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\BellalunAuto"; Filename: "{app}\BellalunAuto.exe"; WorkingDir: "{app}"
Name: "{group}\사용 안내"; Filename: "{app}\사용안내.txt"
Name: "{autodesktop}\BellalunAuto"; Filename: "{app}\BellalunAuto.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Registry]
Root: HKLM64; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\BellalunAuto.exe"; ValueType: string; ValueName: ""; ValueData: "{app}\BellalunAuto.exe"; Flags: uninsdeletekey
Root: HKLM64; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\BellalunAuto.exe"; ValueType: string; ValueName: "Path"; ValueData: "{app}"

; There is intentionally no [Run] section: install never starts a product test.
; There is no recursive [UninstallDelete]: user workspaces are never removed.
[Code]
const
  EnvironmentKey = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';
  OwnershipKey = 'Software\BellalunAuto\Installer';

function NormalizeToken(Value: String): String;
begin
  Value := Trim(Value);
  if (Length(Value) >= 2) and (Value[1] = '"') and (Value[Length(Value)] = '"') then
    Value := Copy(Value, 2, Length(Value) - 2);
  Result := RemoveBackslashUnlessRoot(Value);
end;

function HasToken(Value, Token: String): Boolean;
var
  Parts: TArrayOfString;
  I: Integer;
begin
  Result := False;
  Parts := SplitString(Value, ';');
  for I := 0 to GetArrayLength(Parts) - 1 do
    if CompareText(NormalizeToken(Parts[I]), NormalizeToken(Token)) = 0 then
    begin
      Result := True;
      Exit;
    end;
end;

function RemoveOwnedToken(Value, Token: String): String;
var
  Parts: TArrayOfString;
  I: Integer;
  First: Boolean;
begin
  Result := '';
  First := True;
  Parts := SplitString(Value, ';');
  for I := 0 to GetArrayLength(Parts) - 1 do
    if CompareText(NormalizeToken(Parts[I]), NormalizeToken(Token)) <> 0 then
    begin
      if not First then Result := Result + ';';
      Result := Result + Parts[I];
      First := False;
    end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  PathValue, AppToken, PreviousToken: String;
  Owned, Changed: Boolean;
begin
  if CurStep <> ssPostInstall then Exit;
  RegQueryStringValue(HKLM64, EnvironmentKey, 'Path', PathValue);
  RegQueryStringValue(HKLM64, OwnershipKey, 'PathAdded', PreviousToken);
  AppToken := ExpandConstant('{app}');
  Owned := (PreviousToken <> '') and
    (CompareText(NormalizeToken(PreviousToken), NormalizeToken(AppToken)) = 0);
  Changed := False;
  if (PreviousToken <> '') and not Owned then
  begin
    PathValue := RemoveOwnedToken(PathValue, PreviousToken);
    Changed := True;
  end;
  if not HasToken(PathValue, AppToken) then
  begin
    if (PathValue <> '') and (PathValue[Length(PathValue)] <> ';') then
      PathValue := PathValue + ';';
    PathValue := PathValue + AppToken;
    Owned := True;
    Changed := True;
  end;
  if Changed then
    if not RegWriteExpandStringValue(HKLM64, EnvironmentKey, 'Path', PathValue) then
      RaiseException('시스템 PATH를 저장하지 못했습니다.');
  if Owned then
  begin
    if not RegWriteStringValue(HKLM64, OwnershipKey, 'PathAdded', AppToken) then
      RaiseException('PATH 소유권을 기록하지 못했습니다.');
  end
  else
    RegDeleteValue(HKLM64, OwnershipKey, 'PathAdded');
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PathValue, OwnedToken: String;
begin
  if CurUninstallStep <> usPostUninstall then Exit;
  if RegQueryStringValue(HKLM64, OwnershipKey, 'PathAdded', OwnedToken) and (OwnedToken <> '') then
  begin
    RegQueryStringValue(HKLM64, EnvironmentKey, 'Path', PathValue);
    if not RegWriteExpandStringValue(HKLM64, EnvironmentKey, 'Path',
        RemoveOwnedToken(PathValue, OwnedToken)) then
      RaiseException('시스템 PATH 항목을 제거하지 못했습니다.');
  end;
  RegDeleteKeyIncludingSubkeys(HKLM64, OwnershipKey);
end;
