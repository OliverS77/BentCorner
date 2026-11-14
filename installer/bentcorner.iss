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
; 0.9.9 (Oliver 13.11.: „den installer auch in dark mode“): always dark, like the app; Inno 6.6+ (installed 6.7.3)
WizardStyle=modern dark
; language first (de/en) – passed on to the app with the storage location (installer.json, library's setup plan)
ShowLanguageDialog=yes
; a welcome page with the big wizard image (the brand mark, Gordon 14.11.) – Inno 6 leaves it out by default
DisableWelcomePage=no
; no "Ready to install" page (Gordon 14.11.: it only repeated the desktop tick) – "Installieren" sits on the page before
DisableReadyPage=yes
#ifdef SmallImage
WizardSmallImageFile={#SmallImage}
#endif
#ifdef BigImage
WizardImageFile={#BigImage}
#endif
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
; ticked by default (Oliver/lead 13.11.)
; only the tick, no group heading (Gordon 14.11.: less text)
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"

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

[Messages]
; Gordon 14.11.2026: German always "du" (Inno's German.isl says "Sie" – every such text is replaced here, also the
; error and rare cases) and less text: welcome, desktop page and finished page one line each, in both languages
de.WelcomeLabel1=[name]
de.WelcomeLabel2=Installiert [name/ver] auf deinem PC.
de.ClickNext=
de.WizardSelectTasks=Verknüpfung
de.SelectTasksDesc=
de.SelectTasksLabel2=
de.FinishedHeadingLabel=[name] ist installiert.
de.FinishedLabel=
de.FinishedLabelNoIcons=
de.ClickFinish=
en.WelcomeLabel1=[name]
en.WelcomeLabel2=Installs [name/ver] on your PC.
en.ClickNext=
en.WizardSelectTasks=Shortcut
en.SelectTasksDesc=
en.SelectTasksLabel2=
en.FinishedHeadingLabel=[name] is installed.
en.FinishedLabel=
en.FinishedLabelNoIcons=
en.ClickFinish=
de.SetupLdrStartupMessage=%1 wird jetzt installiert. Möchtest du fortfahren?
de.SetupFileMissing=Die Datei %1 fehlt im Installationsordner. Bitte behebe das Problem oder besorge dir eine neue Kopie des Programms.
de.SetupFileCorrupt=Die Setup-Dateien sind beschädigt. Bitte besorge dir eine neue Kopie des Programms.
de.SetupFileCorruptOrWrongVer=Die Setup-Dateien sind beschädigt oder passen nicht zu dieser Version des Setups. Bitte behebe das Problem oder besorge dir eine neue Kopie des Programms.
de.WindowsVersionNotSupported=Dieses Programm unterstützt die Windows-Version auf deinem PC nicht.
de.AdminPrivilegesRequired=Du musst als Administrator angemeldet sein, um dieses Programm zu installieren.
de.PowerUserPrivilegesRequired=Du musst als Administrator oder als Mitglied der Hauptbenutzer-Gruppe angemeldet sein, um dieses Programm zu installieren.
de.SetupAppRunningError=Das Setup hat entdeckt, dass %1 gerade läuft.%n%nBitte schließe jetzt alle laufenden Fenster davon und klicke auf „OK“, um fortzufahren, oder auf „Abbrechen“, um zu beenden.
de.UninstallAppRunningError=Die Deinstallation hat entdeckt, dass %1 gerade läuft.%n%nBitte schließe jetzt alle laufenden Fenster davon und klicke auf „OK“, um fortzufahren, oder auf „Abbrechen“, um zu beenden.
de.PrivilegesRequiredOverrideInstruction=Bitte wähle, wie installiert wird
de.PrivilegesRequiredOverrideText1=%1 kann für alle Benutzer (braucht Administratorrechte) oder nur für dich installiert werden.
de.PrivilegesRequiredOverrideText2=%1 kann nur für dich oder für alle Benutzer (braucht Administratorrechte) installiert werden.
de.PrivilegesRequiredOverrideCurrentUser=Nur für &mich installieren
de.PrivilegesRequiredOverrideCurrentUserRecommended=Nur für &mich installieren (empfohlen)
de.ExitSetupMessage=Das Setup ist noch nicht fertig. Wenn du jetzt beendest, wird das Programm nicht installiert.%n%nDu kannst das Setup später noch einmal starten.%n%nSetup beenden?
de.SelectLanguageLabel=Wähle die Sprache für die Installation:
de.BrowseDialogLabel=Wähle einen Ordner und klicke auf „OK“.
de.PasswordLabel3=Bitte gib das Passwort ein und klicke auf „Weiter“. Achte auf Groß- und Kleinschreibung.
de.IncorrectPassword=Das Passwort stimmt nicht. Bitte versuche es noch einmal.
de.LicenseLabel=Bitte lies die folgenden wichtigen Informationen, bevor du fortfährst.
de.LicenseLabel3=Bitte lies die folgenden Lizenzbedingungen. Mit der Bildlaufleiste oder der Taste „Bild ab“ kommst du weiter.
de.InfoBeforeLabel=Bitte lies die folgenden wichtigen Informationen, bevor du fortfährst.
de.InfoBeforeClickLabel=Klicke auf „Weiter“, sobald du bereit bist.
de.InfoAfterLabel=Bitte lies die folgenden wichtigen Informationen, bevor du fortfährst.
de.InfoAfterClickLabel=Klicke auf „Weiter“, sobald du bereit bist.
de.UserInfoDesc=Bitte trage deine Daten ein.
de.UserInfoNameRequired=Du musst einen Namen eintragen.
de.SelectDirBrowseLabel=Klicke auf „Weiter“, um fortzufahren, oder auf „Durchsuchen“, um einen anderen Ordner zu wählen.
de.CannotInstallToUNCPath=Das Setup kann nicht in einen UNC-Pfad installieren. Für ein Netzlaufwerk ordne dem Netzwerkpfad bitte einen Laufwerksbuchstaben zu.
de.InvalidPath=Bitte gib einen vollständigen Pfad mit Laufwerksbuchstaben an, z. B.:%n%nC:\Beispiel%n%noder einen UNC-Pfad in der Form:%n%n\\Server\Freigabe
de.InvalidDrive=Das Laufwerk bzw. der UNC-Pfad existiert nicht oder ist nicht erreichbar. Bitte wähle einen anderen Ordner.
de.DiskSpaceWarning=Das Setup braucht mindestens %1 KB freien Speicherplatz, auf dem gewählten Laufwerk sind aber nur %2 KB frei.%n%nMöchtest du trotzdem fortfahren?
de.DirExists=Den Ordner%n%n%1%n%ngibt es schon. Möchtest du trotzdem in diesen Ordner installieren?
de.SelectComponentsLabel2=Wähle die Teile, die du installieren möchtest, und klicke auf „Weiter“.
de.NoUninstallWarning=Das Setup hat festgestellt, dass diese Teile schon auf deinem PC installiert sind:%n%n%1%n%nDass du sie abgewählt hast, entfernt sie nicht.%n%nMöchtest du trotzdem fortfahren?
de.SelectStartMenuFolderBrowseLabel=Klicke auf „Weiter“, um fortzufahren, oder auf „Durchsuchen“, um einen anderen Ordner zu wählen.
de.MustEnterGroupName=Du musst einen Ordnernamen eingeben.
de.ReadyLabel1=Das Setup ist bereit, [name] auf deinem PC zu installieren.
de.ReadyLabel2a=Klicke auf „Installieren“, um zu beginnen, oder auf „Zurück“, um deine Einstellungen zu ändern.
de.ReadyLabel2b=Klicke auf „Installieren“, um zu beginnen.
de.StopDownload=Möchtest du den Download wirklich abbrechen?
de.StopExtraction=Möchtest du das Entpacken wirklich abbrechen?
de.PreviousInstallNotCompleted=Eine frühere Installation oder Deinstallation ist nicht fertig geworden. Dafür muss der PC neu gestartet werden.%n%nStarte das Setup nach dem Neustart noch einmal, um [name] zu installieren.
de.CannotContinue=Das Setup kann nicht fortfahren. Bitte klicke auf „Abbrechen“.
de.PrepareToInstallNeedsRestart=Das Setup muss deinen PC neu starten. Starte das Setup danach noch einmal, um die Installation von [name] abzuschließen.%n%nJetzt neu starten?
de.InstallingLabel=Bitte warte, während [name] auf deinem PC installiert wird.
de.FinishedRestartLabel=Um [name] fertig zu installieren, muss das Setup deinen PC neu starten. Jetzt neu starten?
de.FinishedRestartMessage=Um [name] fertig zu installieren, muss das Setup deinen PC neu starten.%n%nJetzt neu starten?
de.SelectDiskLabel2=Bitte lege Datenträger %1 ein und klicke auf „OK“.%n%nLiegen die Dateien in einem anderen Ordner als dem angezeigten, gib den richtigen Pfad ein oder klicke auf „Durchsuchen“.
de.SelectDirectoryLabel=Bitte gib an, wo der nächste Datenträger liegt.
de.SetupAborted=Das Setup konnte nicht abgeschlossen werden.%n%nBitte behebe das Problem und starte das Setup noch einmal.
de.ErrorRestartingComputer=Das Setup konnte den PC nicht neu starten. Bitte starte ihn selbst neu.
de.ConfirmUninstall=Möchtest du %1 wirklich entfernen?
de.UninstallStatusLabel=Bitte warte, während %1 von deinem PC entfernt wird.
de.UninstalledAll=%1 wurde von deinem PC entfernt.
de.UninstalledMost=%1 ist entfernt.%n%nEinige Teile konnten nicht entfernt werden – du kannst sie selbst löschen.
de.UninstalledAndNeedsRestart=Um die Deinstallation von %1 abzuschließen, muss dein PC neu gestartet werden.%n%nJetzt neu starten?
de.ConfirmDeleteSharedFile2=Laut System benutzt kein anderes Programm mehr diese gemeinsame Datei. Soll sie entfernt werden?%nFalls doch noch ein Programm sie braucht, läuft es danach vielleicht nicht mehr richtig. Wenn du unsicher bist, wähle „Nein“ – die Datei zu behalten schadet nicht.
de.AddonHostProgramNotFound=%1 wurde im gewählten Ordner nicht gefunden.%n%nMöchtest du trotzdem fortfahren?

[CustomMessages]
de.ForgetTitle=Bent°Corner deinstallieren
en.ForgetTitle=Uninstall Bent°Corner
de.ForgetA=Meine geteilten Listen und Binder auf dem Bent°Corner-Server löschen
en.ForgetA=Delete my shared lists and binders on the Bent°Corner server
de.ForgetASmall=Deine ID und dein Schlüssel bleiben, bis sie 365 Tage nicht genutzt wurden. Päckchen werden nach dem Abholen gelöscht, spätestens nach 14 Tagen.
en.ForgetASmall=Your ID and key remain until they haven't been used for 365 days. Parcels are deleted once picked up, at the latest after 14 days.
; legal 13.11.2026 (Legal/bentcorner/2026-11-13-deinstaller-haken.md) – verbatim
de.ForgetB=Meine Daten auf dem Bent°Corner-Server löschen – deine ID mit Schlüssel, deine Online-Sicherung, geteilte Listen und Binder, Päckchen und Blockaden. Sofort und für alle deine Geräte.
en.ForgetB=Delete my data on the Bent°Corner server – your ID and key, your online backup, shared lists and binders, parcels and blocks. Immediately and for all your devices.
de.ForgetBSmall=Deine anderen Geräte gleichen danach nicht mehr ab, und die Online-Sicherung lässt sich nicht mehr zurückholen – auch nicht mit dem Schutz-Code. Ausnahmen: Meldungen bleiben 180 Tage, die Sicherungen des Servers enthalten die Daten noch bis zu 4 Wochen verschlüsselt (siehe Datenschutz).
en.ForgetBSmall=Your other devices stop syncing afterwards, and the online backup can't be restored any more – not even with the protection code. Exceptions: reports are kept for 180 days, and the server's backups still contain the data, encrypted, for up to 4 weeks (see privacy policy).
de.ForgetStay=Ohne Haken bleiben deine ID und deine Online-Sicherung – du kannst Bent°Corner neu installieren und weitermachen. Nutzt du sie nicht mehr, löschen wir die Online-Sicherung nach 183 Tagen und die ID nach 365 Tagen.
en.ForgetStay=Without the tick your ID and online backup stay – you can reinstall Bent°Corner and carry on. If you don't use them any more, we delete the online backup after 183 days and the ID after 365 days.
de.ForgetGuard=Du hast einen Schutz-Code. Deine Daten auf dem Server löschst du in der App mit „Alles löschen, auch online“ – vor dem Deinstallieren.
en.ForgetGuard=You have a protection code. Delete your data on the server in the app with “Delete everything, also online” – before uninstalling.
; the storage page (0.9.9, library's plan; wording lead 13.11.)
de.HomeTitle=Deine Sammlung
en.HomeTitle=Your collection
de.HomeSub=Wo Bent°Corner deine Sammlung speichert.
en.HomeSub=Where Bent°Corner keeps your collection.
de.HomeLine=Hier liegt deine Sammlung (nicht das Programm):
en.HomeLine=Your collection is kept here (not the program):
de.HomeInApp=Bitte einen Ordner außerhalb des Programmordners wählen – der wird beim Deinstallieren gelöscht.
en.HomeInApp=Please choose a folder outside the program folder – it is deleted when uninstalling.
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
  Friends, Stay, BoxText: TNewStaticText;
  HomePage: TInputDirWizardPage;
  HomeNote: TNewStaticText;

{ A new installation: no data folder noted yet (%APPDATA%\BentCorner\datenordner.json, system/datahome.py). Existing
  users (and updates) get neither the storage page nor installer.json – the app behaves exactly as before. }
function NewInstall: Boolean;
begin
  Result := not FileExists(ExpandConstant('{userappdata}\BentCorner\datenordner.json'));
end;

{ a changed folder takes the note away again – it only belongs to the folder it was about }
procedure HomeEditChange(Sender: TObject);
begin
  HomeNote.Caption := '';
end;

procedure InitializeWizard;
begin
  if not NewInstall then Exit;
  HomePage := CreateInputDirPage(wpSelectTasks, CustomMessage('HomeTitle'), CustomMessage('HomeSub'),
                                 CustomMessage('HomeLine'), False, '');
  HomePage.Add('');
  HomePage.Values[0] := ExpandConstant('{localappdata}\BentCorner');   { Oliver/Gordon 13.11.: no subfolder }
  HomeNote := TNewStaticText.Create(HomePage);   { the only feedback – on the page, never a message box }
  HomeNote.Parent := HomePage.Surface;
  HomeNote.AutoSize := False;
  HomeNote.WordWrap := True;
  HomeNote.SetBounds(0, HomePage.Edits[0].Top + HomePage.Edits[0].Height + ScaleY(16), HomePage.SurfaceWidth, ScaleY(40));
  HomeNote.Caption := '';
  HomePage.Edits[0].OnChange := @HomeEditChange;
end;

{ No Ready page (DisableReadyPage): the last page before installing says "Installieren" on its button – the storage page
  for a new installation, otherwise the desktop page. Inno renames only its own pages, not ours. }
procedure CurPageChanged(CurPageID: Integer);
begin
  if ((HomePage <> nil) and (CurPageID = HomePage.ID)) or ((HomePage = nil) and (CurPageID = wpSelectTasks)) then
    WizardForm.NextButton.Caption := SetupMessage(msgButtonInstall);
end;

function InsideApp(Path: String): Boolean;
var
  A: String;
begin
  A := Uppercase(AddBackslash(ExpandConstant('{app}')));
  Result := Pos(A, Uppercase(AddBackslash(Path))) = 1;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (HomePage <> nil) and (CurPageID = HomePage.ID) then
  begin
    if InsideApp(HomePage.Values[0]) then
    begin
      HomeNote.Caption := CustomMessage('HomeInApp');
      Result := False;
    end
    else
      HomeNote.Caption := '';
  end;
end;

function JsonEscape(S: String): String;
begin
  Result := S;
  StringChangeEx(Result, '\', '\\', True);
  StringChangeEx(Result, '"', '\"', True);
end;

{ Handed to the app's first start (library): only language + folder, read once and deleted there }
procedure CurStepChanged(CurStep: TSetupStep);
var
  Dir: String;
  Line: TArrayOfString;
begin
  if (CurStep <> ssPostInstall) or (HomePage = nil) then Exit;
  Dir := ExpandConstant('{userappdata}\BentCorner');
  ForceDirectories(Dir);
  SetArrayLength(Line, 1);
  Line[0] := '{"v": 1, "lang": "' + ActiveLanguage + '", "home": "' + JsonEscape(HomePage.Values[0]) + '"}';
  { UTF-8 without BOM (library 13.11.): a user name outside the ANSI code page must arrive intact }
  SaveStringsToUTF8FileWithoutBOM(Dir + '\installer.json', Line, False);
end;

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

{ Without the tick: legal's line that ID and online backup stay (and when they go) instead of the friends line }
procedure ServerBoxClick(Sender: TObject);
begin
  if (Friends = nil) or (Stay = nil) then Exit;
  Friends.Visible := ServerBox.Checked;
  Stay.Visible := not ServerBox.Checked;
end;

{ The text next to the box works like the box's own caption }
procedure BoxTextClick(Sender: TObject);
begin
  ServerBox.Checked := not ServerBox.Checked;
end;

{ The uninstaller's one page: the server checkbox – ALWAYS unticked (Oliver/Gordon 13.11., legal's texts) – shown
  unless the program already did it (/BCSERVER=done from „Bent°Corner löschen“) or nothing of ours is on the server.
  A protection code set (program exit 12, net/forget.py): no checkbox – the uninstaller has no code – but legal's line
  to delete in the app first. Silent: no page, no request. }
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
  Form := CreateCustomForm(ScaleX(520), ScaleY(290), False, True);
  try
    Form.Caption := CustomMessage('ForgetTitle');
    Y := ScaleY(16);
    if (Mode = 10) or (Mode = 11) then
    begin
      ServerBox := TNewCheckBox.Create(Form);
      ServerBox.Parent := Form;
      // only the box itself; legal's line next to it as a wrapping text (a checkbox caption cannot wrap and was cut off,
      // pictures 14.11.) – clicking the text ticks the box like its own caption would
      ServerBox.SetBounds(ScaleX(16), Y, ScaleX(18), ScaleY(18));
      ServerBox.Checked := False;
      ServerBox.OnClick := @ServerBoxClick;
      BoxText := TNewStaticText.Create(Form);
      BoxText.Parent := Form;
      BoxText.AutoSize := False;
      BoxText.WordWrap := True;
      BoxText.SetBounds(ScaleX(34), Y + ScaleY(1), Form.ClientWidth - ScaleX(50), ScaleY(36));
      BoxText.OnClick := @BoxTextClick;
      if Mode = 10 then BoxText.Caption := CustomMessage('ForgetB') else BoxText.Caption := CustomMessage('ForgetA');
      Y := Y + ScaleY(42);
      Small := TNewStaticText.Create(Form);
      Small.Parent := Form;
      Small.AutoSize := False;
      Small.WordWrap := True;
      Small.SetBounds(ScaleX(34), Y, Form.ClientWidth - ScaleX(50), ScaleY(52));
      if Mode = 10 then Small.Caption := CustomMessage('ForgetBSmall') else Small.Caption := CustomMessage('ForgetASmall');
      Y := Y + ScaleY(60);
      Friends := TNewStaticText.Create(Form);
      Friends.Parent := Form;
      Friends.AutoSize := False;
      Friends.WordWrap := True;
      Friends.SetBounds(ScaleX(34), Y, Form.ClientWidth - ScaleX(50), ScaleY(52));
      Friends.Caption := CustomMessage('ForgetFriends');
      Stay := TNewStaticText.Create(Form);
      Stay.Parent := Form;
      Stay.AutoSize := False;
      Stay.WordWrap := True;
      Stay.SetBounds(ScaleX(34), Y, Form.ClientWidth - ScaleX(50), ScaleY(52));
      Stay.Caption := CustomMessage('ForgetStay');
      ServerBoxClick(nil);
      Y := Y + ScaleY(60);
    end
    else if Mode = 12 then
    begin
      Small := TNewStaticText.Create(Form);
      Small.Parent := Form;
      Small.AutoSize := False;
      Small.WordWrap := True;
      Small.SetBounds(ScaleX(16), Y, Form.ClientWidth - ScaleX(32), ScaleY(52));
      Small.Caption := CustomMessage('ForgetGuard');
      Y := Y + ScaleY(58);
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
