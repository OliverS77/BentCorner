; Bent°Corner installer (labs/installer/PLAN.md, Oliver 03.11.2026: "Installer ja"). Inno Setup 6.3+:
;   ISCC.exe /DAppVersion=0.9.8 /DSrcDir=..\dist\BentCorner /DIconFile=..\brand\icon.ico installer\bentcorner.iss
; Per user, no administrator rights: %LOCALAPPDATA%\Programs\Bent°Corner (a fixed path – Windows keeps the tray icon per
; path), Start menu entry, own uninstaller (Apps & Features, HKCU only). The data folder is never touched here – the
; program keeps finding it through %APPDATA%\BentCorner\datenordner.json as before.
; Updates: the program's updater checks the signed manifest + sha256, then runs this setup silently with
;   /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER /CLOSEAPPLICATIONS /RESTARTAPP=1
; Uninstalling: one page with the server checkbox („Bent°Corner löschen“, texts legal 03.11.2026 – PLAN.md § 8); it runs
; `BentCorner.exe --forget-server`, which sends only the deletion request, nothing else.

#ifndef AppVersion
  #error AppVersion missing: ISCC /DAppVersion=<version>
#endif
#ifndef SrcDir
  #define SrcDir "..\dist\BentCorner"
#endif
#ifndef IconFile
  #define IconFile "..\brand\icon.ico"
#endif
#ifndef OutDir
  #define OutDir "..\dist"
#endif
#define AppName "Bent°Corner"

[Setup]
AppId={{6E2B4F1A-8C37-4D0B-9A51-B3C0E7D2F914}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Oliver Schunn
AppPublisherURL=https://bentcorner.app
AppSupportURL=https://bentcorner.app
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
UsePreviousAppDir=yes
OutputDir={#OutDir}
OutputBaseFilename=BentCorner-Setup-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\BentCorner.exe
UninstallDisplayName={#AppName}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
VersionInfoCompany=Oliver Schunn
VersionInfoDescription={#AppName} Setup
VersionInfoCopyright=© 2026 Oliver Schunn
#ifdef Sign
; signed builds (Certum, tools\sign.py): ISCC /DSign /Sbcsign="<signer> $f" – signs the setup and unins000.exe
SignTool=bcsign
SignedUninstaller=yes
#endif

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; the previous version's program files (folder <version>-<build time>) – only ours, inside {app}
Type: filesandordirs; Name: "{app}\0.*"
Type: filesandordirs; Name: "{app}\1.*"

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\{#AppName}"; Filename: "{app}\BentCorner.exe"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\BentCorner.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BentCorner.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; a silent update started by the program: start it again afterwards
Filename: "{app}\BentCorner.exe"; Flags: nowait; Check: RestartWanted

[Registry]
; the autostart entry the program sets on request (ui/tray.py) – removed with the program
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "BentCorner"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

; No [UninstallDelete] "{app}" any more (lead 06.11.2026): the uninstaller removes the files it installed; what is left
; in the folder goes only when no collection lies there (CurUninstallStepChanged below)

[CustomMessages]
de.ForgetTitle=Bent°Corner deinstallieren
en.ForgetTitle=Uninstall Bent°Corner
de.ForgetA=Meine geteilten Listen und Binder auf dem Bent°Corner-Server löschen
en.ForgetA=Delete my shared lists and binders on the Bent°Corner server
de.ForgetASmall=Deine ID und dein Schlüssel bleiben, bis sie 365 Tage nicht genutzt wurden. Päckchen werden nach dem Abholen gelöscht, spätestens nach 14 Tagen.
en.ForgetASmall=Your ID and key remain until they haven't been used for 365 days. Parcels are deleted once picked up, at the latest after 14 days.
de.ForgetB=Meine Daten auf dem Bent°Corner-Server löschen – deine ID mit Schlüssel, geteilte Listen und Binder, Päckchen und Blockaden. Sofort.
en.ForgetB=Delete my data on the Bent°Corner server – your ID and key, shared lists and binders, parcels and blocks. Immediately.
de.ForgetBSmall=Ausnahmen: Meldungen bleiben 180 Tage, die Sicherungen des Servers enthalten die Daten noch bis zu 4 Wochen verschlüsselt (siehe Datenschutz).
en.ForgetBSmall=Exceptions: reports are kept for 180 days, and the server's backups still contain the data, encrypted, for up to 4 weeks (see privacy policy).
de.ForgetFriends=Deine Freunde sehen deine geteilten Listen und Binder danach nicht mehr.
en.ForgetFriends=Your friends will no longer see your shared lists and binders.
de.ForgetKeep=Deine Sammlung bleibt in deinem Datenordner.
en.ForgetKeep=Your collection stays in your data folder.
de.ForgetGo=Deinstallieren
en.ForgetGo=Uninstall
de.ForgetCancel=Abbrechen
en.ForgetCancel=Cancel
de.ForgetDone=Gelöscht.
en.ForgetDone=Deleted.
de.ForgetAlready=War bereits gelöscht.
en.ForgetAlready=Was already deleted.
de.ForgetFailed=Deine Daten auf dem Server sind NICHT gelöscht. Ohne Nutzung löscht der Server sie automatisch: geteilte Listen und Binder 6 Monate nach dem letzten Teilen, deine ID und dein Schlüssel nach 365 Tagen, Päckchen nach dem Abholen, spätestens nach 14 Tagen. Sofort geht es per Mail an hello@bentcorner.app.
en.ForgetFailed=Your data on the server is NOT deleted. Without use, the server deletes it automatically: shared lists and binders 6 months after they were last shared, your ID and key after 365 days, parcels once picked up, at the latest after 14 days. To have it deleted right away, email hello@bentcorner.app.
de.ForgetYourId=Deine ID: %1 (bitte in der Mail angeben)
en.ForgetYourId=Your ID: %1 (please include it in the email)

[Code]
var
  ServerBox: TNewCheckBox;
  ForgetResult: String;

function RestartWanted: Boolean;
begin
  Result := WizardSilent and (ExpandConstant('{param:RESTARTAPP|0}') = '1');
end;

{ The program answers which version of the server checkbox applies (net/forget.py):
  exit 10 = B (/v1/forget live), 11 = A (lists and binders only), 4 = nothing of ours on the server }
function ForgetMode: Integer;
var
  Code: Integer;
begin
  Result := 4;
  if FileExists(ExpandConstant('{app}\BentCorner.exe')) then
    if Exec(ExpandConstant('{app}\BentCorner.exe'), '--forget-server --check', '', SW_HIDE, ewWaitUntilTerminated, Code) then
      Result := Code;
end;

{ The one deletion request; its JSON line tells the result and the own ID }
function RunForget: String;
var
  Res: TExecOutput;
  Code: Integer;
begin
  Result := '';
  if ExecAndCaptureOutput(ExpandConstant('{app}\BentCorner.exe'), '--forget-server', '', SW_HIDE,
                          ewWaitUntilTerminated, Code, Res) then
    if GetArrayLength(Res.StdOut) > 0 then
      Result := Res.StdOut[GetArrayLength(Res.StdOut) - 1];
end;

function JsonValue(Line, Key: String): String;
var
  P: Integer;
begin
  Result := '';
  P := Pos('"' + Key + '": "', Line);
  if P = 0 then Exit;
  Result := Copy(Line, P + Length(Key) + 5, Length(Line));
  P := Pos('"', Result);
  if P > 0 then Result := Copy(Result, 1, P - 1);
end;

{ The uninstaller's one page: the server checkbox (pre-selected, legal), shown unless the program already did it
  (/BCSERVER=done from „Bent°Corner löschen“) or nothing of ours is on the server. Silent: no page, no request. }
function InitializeUninstall: Boolean;
var
  Form: TSetupForm;
  Small, Friends, Keep: TNewStaticText;
  Go, Cancel: TNewButton;
  Mode, Y: Integer;
begin
  Result := True;
  ForgetResult := '';
  if UninstallSilent or (ExpandConstant('{param:BCSERVER|}') = 'done') then Exit;
  Mode := ForgetMode;
  Form := CreateCustomForm(ScaleX(520), ScaleY(260), False, True);
  try
    Form.Caption := CustomMessage('ForgetTitle');
    Y := ScaleY(16);
    if (Mode = 10) or (Mode = 11) then
    begin
      ServerBox := TNewCheckBox.Create(Form);
      ServerBox.Parent := Form;
      ServerBox.SetBounds(ScaleX(16), Y, Form.ClientWidth - ScaleX(32), ScaleY(36));
      ServerBox.Checked := True;
      if Mode = 10 then ServerBox.Caption := CustomMessage('ForgetB') else ServerBox.Caption := CustomMessage('ForgetA');
      Y := Y + ScaleY(42);
      Small := TNewStaticText.Create(Form);
      Small.Parent := Form;
      Small.AutoSize := False;
      Small.WordWrap := True;
      Small.SetBounds(ScaleX(34), Y, Form.ClientWidth - ScaleX(50), ScaleY(44));
      if Mode = 10 then Small.Caption := CustomMessage('ForgetBSmall') else Small.Caption := CustomMessage('ForgetASmall');
      Y := Y + ScaleY(48);
      Friends := TNewStaticText.Create(Form);
      Friends.Parent := Form;
      Friends.AutoSize := False;
      Friends.WordWrap := True;
      Friends.SetBounds(ScaleX(34), Y, Form.ClientWidth - ScaleX(50), ScaleY(32));
      Friends.Caption := CustomMessage('ForgetFriends');
      Y := Y + ScaleY(36);
    end;
    Keep := TNewStaticText.Create(Form);
    Keep.Parent := Form;
    Keep.SetBounds(ScaleX(16), Y, Form.ClientWidth - ScaleX(32), ScaleY(20));
    Keep.Caption := CustomMessage('ForgetKeep');
    Go := TNewButton.Create(Form);
    Go.Parent := Form;
    Go.Caption := CustomMessage('ForgetGo');
    Go.ModalResult := mrOk;
    Go.SetBounds(Form.ClientWidth - ScaleX(220), Form.ClientHeight - ScaleY(40), ScaleX(100), ScaleY(26));
    Cancel := TNewButton.Create(Form);
    Cancel.Parent := Form;
    Cancel.Caption := CustomMessage('ForgetCancel');
    Cancel.ModalResult := mrCancel;
    Cancel.SetBounds(Form.ClientWidth - ScaleX(112), Form.ClientHeight - ScaleY(40), ScaleX(96), ScaleY(26));
    if Form.ShowModal <> mrOk then
    begin
      Result := False;
      Exit;
    end;
    if (ServerBox <> nil) and ServerBox.Checked then
      ForgetResult := RunForget;
  finally
    Form.Free;
  end;
end;

{ After the installed files are gone: the rest of the program folder too – but never a collection. The program never
  keeps its data here (system/datahome.py), this is the second safeguard: settings.json or data\ in the folder -> the
  folder stays as it is. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  App: String;
begin
  if CurUninstallStep <> usPostUninstall then Exit;
  App := ExpandConstant('{app}');
  if FileExists(App + '\settings.json') or DirExists(App + '\data') then Exit;
  DelTree(App, True, True, True);
end;

{ After uninstalling: the server part's result in plain words – "Deleted" only when the server confirmed it }
procedure DeinitializeUninstall;
var
  Status, Code, Text: String;
begin
  if ForgetResult = '' then Exit;
  Status := JsonValue(ForgetResult, 'status');
  Code := JsonValue(ForgetResult, 'code');
  if Status = 'deleted' then Text := CustomMessage('ForgetDone')
  else if Status = 'already' then Text := CustomMessage('ForgetAlready')
  else begin
    Text := CustomMessage('ForgetFailed');
    if Code <> '' then Text := Text + #13#10#13#10 + FmtMessage(CustomMessage('ForgetYourId'), [Code]);
  end;
  MsgBox(Text, mbInformation, MB_OK);
end;
