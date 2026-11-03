# Baut dist\BentCorner.exe
#   powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
# PyInstaller sucht fehlende DLLs auch im PATH – conda/msys/mingw (z. B. über das PowerShell-Profil) brachten so 43 fremde
# DLLs in die exe (0.9.7.4). Darum hier raus aus dem PATH; tools\check_binaries.py prüft nach dem Bauen zusätzlich.
$env:PATH = (($env:PATH -split ';') | Where-Object { $_ -and $_ -notmatch '(?i)conda|msys|mingw' }) -join ';'

if (-not (Test-Path .venv)) {
    python -m venv .venv
}
# Pakete: pip nur, wenn sich requirements.txt / die Paket-Zeilen hier geändert haben oder die Prüfung unten etwas
# vermisst. Hintergrund (0.9.2.42): pip lief, während die Owner-Konsole cffi geladen hatte – WinError 5 mitten im
# Umbau, certifi/cffi/charset_normalizer halb gelöscht, und die exe wurde trotzdem gebaut (ohne Netz).
$Onnx = "onnxruntime-directml==1.24.4"
$ReqHash = (Get-FileHash requirements.txt -Algorithm SHA256).Hash + "|pyinstaller|$Onnx"
$ReqFile = ".venv\req.sha"
# Alles, ohne das die exe kaputt wäre (Netz, Signaturen, Freunde, SCAN° auf der Grafikkarte, Bauen)
$VenvCheck = "import certifi, charset_normalizer, requests, cffi, nacl.signing, cryptography, PySide6, cv2, numpy, " +
             "rapidocr_onnxruntime, PyInstaller, onnxruntime as o; " +
             "assert 'DmlExecutionProvider' in o.get_available_providers(), 'onnxruntime ohne DirectML'"
function Test-Venv {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    .\.venv\Scripts\python.exe -c $VenvCheck 2>$null | Out-Null
    $ok = ($LASTEXITCODE -eq 0); $ErrorActionPreference = $old
    return $ok
}
function Invoke-Pip {
    .\.venv\Scripts\python.exe -m pip @args
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $ReqFile -ErrorAction SilentlyContinue
        throw "pip fehlgeschlagen (pip $args) – .venv ist evtl. halb umgebaut, keine exe gebaut"
    }
}
$saved = if (Test-Path $ReqFile) { (Get-Content $ReqFile -Raw).Trim() } else { "" }
if ($saved -eq $ReqHash -and (Test-Venv)) {
    Write-Host "Pakete unverändert – pip übersprungen"
} elseif (-not (Test-Path $ReqFile) -and (Test-Path .venv\Scripts\python.exe) -and (Test-Venv)) {
    # Erster Lauf mit dieser Prüfung: vollständige .venv übernehmen statt pip (sonst bliebe jeder Build an einer
    # offenen Owner-Konsole hängen). Ändert sich requirements.txt später, läuft pip wie unten.
    Set-Content $ReqFile $ReqHash -Encoding ascii
    Write-Host "Pakete vollständig – Stand übernommen (.venv\req.sha), pip übersprungen"
} else {
    # pip ersetzt Dateien – läuft dabei ein Python aus dieser .venv (Owner-Konsole, Tests, App aus dem Quellcode),
    # sind dessen Dateien gesperrt und pip bricht mittendrin ab. Also vorher stoppen.
    $venv = (Resolve-Path .venv).Path
    $busy = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($venv, [StringComparison]::OrdinalIgnoreCase) }
    if ($busy) {
        $list = ($busy | ForEach-Object { "  PID $($_.ProcessId): $($_.CommandLine)" }) -join "`n"
        throw "Pakete müssen neu installiert werden, aber Python aus dieser .venv läuft noch:`n$list`n" +
              "Bitte schließen (z. B. die Owner-Konsole) und build.ps1 nochmal starten."
    }
    Write-Host "Pakete werden installiert/geprüft ..."
    Invoke-Pip install -q -r requirements.txt pyinstaller
    # SCAN° auf der Grafikkarte (DirectML, jede DirectX-12-Karte; ohne passende Karte rechnet es wie bisher auf dem
    # Prozessor). Ersetzt das reine Prozessor-Paket, das die Texterkennung als Abhängigkeit mitbringt. Die
    # DirectML.dll aus dem Paket kommt NICHT in die exe (tools\pyinstaller-hooks) – die App nimmt die aus Windows.
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    .\.venv\Scripts\python.exe -m pip uninstall -y -q onnxruntime 2>$null | Out-Null   # fehlt es, ist das ok
    $ErrorActionPreference = $old
    Invoke-Pip install -q --no-deps --force-reinstall $Onnx
    if (-not (Test-Venv)) { throw ".venv unvollständig nach pip (Prüfung: $VenvCheck) – keine exe gebaut" }
    Set-Content $ReqFile $ReqHash -Encoding ascii
}
# SCAN°-Netz DINOv2 (Apache-2.0) von Hugging Face, fester Stand + sha256 – so baut auch der öffentliche Quellcode (ohne
# models\) genau dieselbe exe: dinov2-small-q = model_quantized (Prozessor), fp16 = dasselbe Netz ungepackt (Grafikkarte)
$HfDino = "https://huggingface.co/Xenova/dinov2-small/resolve/c2bb04a51fab207c420665f1946016107bffc701/onnx"
$Models = @{
    "dinov2-small-q.onnx"    = @("model_quantized.onnx", "3AFDC8BC63B50558D6E5770F5B799BB82455C2311183A2DE43803F343A29D917")
    "dinov2-small-fp16.onnx" = @("model_fp16.onnx", "4E9EA6FE106E2225E28EE3C1C3D53B5B92AA4AF62142F6ED6B66B6A92213CF04")
}
New-Item -ItemType Directory -Force models | Out-Null
foreach ($name in $Models.Keys) {
    $src, $sha = $Models[$name]
    if (-not (Test-Path models\$name)) { Invoke-WebRequest "$HfDino/$src" -OutFile models\$name }
    if ((Get-FileHash models\$name -Algorithm SHA256).Hash -ne $sha) { throw "models\$name hat nicht den erwarteten sha256" }
}
# Fingerabdruck-Index aller Karten nach models\ – Quelle für tools\publish_packs.py, kommt NICHT in die .exe: die Indizes
# und die Pokémon-Daten lädt das Programm als Datenpaket vom eigenen Server (packs.py)
if (Test-Path data\fp_build\fingerprints-all.npz) {
    Copy-Item data\fp_build\fingerprints-all.npz models\fingerprints-all.npz -Force
} else {
    Write-Host "Hinweis: kein Fingerabdruck-Index aller Karten (tools\build_fingerprints.py) - nur geladene Sets."
}

# Vor dem Bauen: jede Python-Datei muss sich übersetzen lassen – sonst landet eine kaputte Datei in der .exe und das
# Programm startet nicht (PyInstaller selbst meckert dabei nicht)
.\.venv\Scripts\python.exe -c "import ast, pathlib; [ast.parse(f.read_text('utf-8'), str(f)) for f in [*pathlib.Path('.').glob('*.py'), *[f for d in ('games', 'scanner', 'cards', 'collection', 'net', 'ui', 'system', 'locales') for f in pathlib.Path(d).glob('*.py')]]]"
if ($LASTEXITCODE -ne 0) { throw "Python-Datei kaputt (Syntaxfehler) - nicht gebaut" }

# comtypes legt sein Paket comtypes.gen erst beim ersten Kamera-Zugriff an – in einer frischen .venv fehlt es, und die
# exe würde es zur Laufzeit im Programmordner anlegen. Hier immer vorher anlegen: jede .venv baut dieselbe exe.
.\.venv\Scripts\python.exe -c "from comtypes.client import _code_cache as c; c._create_comtypes_gen_package()"
if ($LASTEXITCODE -ne 0) { throw "comtypes.gen nicht angelegt" }

# Versionsnummer aus version.py in die Versionsinfos der .exe
.\.venv\Scripts\python.exe version.py

# Badges & Collectibles: Muster-Ticket + Code, wenn sich am Ticket etwas geändert hat (assets\collectibles)
.\.venv\Scripts\python.exe tools\ticket_snapshot.py

# Programmsymbol aus dem Logo-Paket brand\logo (16-24 Pixelbilder, ab 32 aus den SVG – ui/iconkit.py) nach brand\icon.ico.
# Die Marke (brand\) ist nicht GPL: ohne den Ordner (Forks) ein neutrales Platzhalter-Symbol in build\ und kein Logo
if (Test-Path brand\logo) {
    .\.venv\Scripts\python.exe -m ui.iconkit
    $Icon = "brand\icon.ico"; $Brand = @("--add-data", "brand;brand")
} else {
    .\.venv\Scripts\python.exe -m ui.iconkit build\icon.ico
    $Icon = "build\icon.ico"; $Brand = @()
}
if ($LASTEXITCODE -ne 0) { throw "Programmsymbol nicht gebaut (ui/iconkit.py)" }

# Kennung dieses Builds (Version + Zeitstempel): Ordnername der Programmdateien in „Bent°Corner Essentials“. Die
# kleine BentCorner.exe liegt dort an einem FESTEN Ort, ihre Dateien im Ordner mit der Kennung (--contents-directory) –
# so bleibt der Pfad des laufenden Programms über Updates gleich (Windows merkt sich das Tray-Symbol je Pfad)
# Lizenztexte der Bausteine nach licenses\ (LGPL für Qt/FFmpeg/GEOS, Python, OpenCV, ONNX Runtime, jedes Paket) – in der
# App ohne Internet lesbar (Einstellungen → Rechtliches → Hinweise zu Drittanbietern); THIRD_PARTY_NOTICES verweist darauf
.\.venv\Scripts\python.exe tools\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw "Lizenztexte nicht gesammelt (tools\collect_licenses.py) – nicht gebaut" }
$LicenseDir = @("--add-data", "licenses;licenses")
$BuildId = (.\.venv\Scripts\python.exe -c "import version, datetime; print(version.VERSION + '-' + datetime.datetime.now().strftime('%y%m%d%H%M'))").Trim()
$env:BC_BUILD_ID = $BuildId
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onedir --noupx --windowed `
    --name BentCorner --icon $Icon --version-file version_info.txt --contents-directory $BuildId `
    --exclude-module tkinter `
    --add-data "setliste.json;." `
    --add-data "THIRD_PARTY_NOTICES.md;." `
    --add-data "LICENSE;." `
    --add-data "LICENSE-ASSETS.md;." `
    @LicenseDir `
    --add-data "fonts;fonts" `
    --add-data "assets;assets" `
    @Brand `
    --add-data "models\dinov2-small-q.onnx;models" `
    --add-data "models\dinov2-small-fp16.onnx;models" `
    --add-data "qml;qml" `
    --collect-all rapidocr_onnxruntime `
    --additional-hooks-dir tools\pyinstaller-hooks `
    --collect-submodules games `
    --collect-submodules scanner --collect-submodules cards --collect-submodules collection `
    --collect-submodules net --collect-submodules ui --collect-submodules system `
    --hidden-import _cffi_backend `
    --collect-all nacl `
    app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller fehlgeschlagen" }
# Fehlt PyInstaller ein Paket, baut es trotzdem – die exe startet, aber ohne Netz/Signaturen. Also hier stoppen.
# Nur das Paket selbst zählt („missing module named certifi - …“); fehlende optionale Untermodule
# (cryptography.x509.UnsupportedExtension …) sind normal.
$warn = Select-String -Path build\BentCorner\warn-BentCorner.txt -Pattern `
    "missing module named '?(certifi|charset_normalizer|cffi|_cffi_backend|nacl|requests|urllib3|cryptography)'? - " |
    Select-Object -First 5
if ($warn) { throw "Wichtiges Paket fehlt in der exe:`n$($warn.Line -join "`n")" }
# Keine proprietäre GPU-Bibliothek in der exe (Signatur/Open Source, 0.9.7.4): DirectML kommt aus Windows selbst.
# Feste Prüfung – egal auf welchem Weg (Hook, Abhängigkeits-Analyse) eine DirectML*.dll hineingeraten ist.
$dml = Get-ChildItem dist\BentCorner -Recurse -File -Filter "DirectML*.dll" -ErrorAction SilentlyContinue
if ($dml) { throw "DirectML.dll darf nicht in die exe:`n$(($dml.FullName) -join "`n")" }
# Jede DLL/.pyd nur aus venv, Python oder Windows – sonst kam sie zufällig über den PATH (Liste in der Meldung)
$foreign = .\.venv\Scripts\python.exe tools\check_binaries.py build\BentCorner\COLLECT-00.toc
if ($LASTEXITCODE -ne 0) { throw "Fremde Bibliotheken in der exe – nicht gebaut:`n$($foreign -join "`n")" }

# Eine einzelne exe zum Verteilen: Starter (launcher\Launcher.cs) + das Programm als Zip dahinter. Der Starter legt
# es einmal je Version in „Bent°Corner Essentials“ neben den Daten ab und startet danach direkt von dort.
.\.venv\Scripts\python.exe tools\build_launcher.py
if ($LASTEXITCODE -ne 0) { throw "Starter fehlgeschlagen" }
# Dieselbe Prüfung im fertigen Paket (Zip hinter dem Starter)
.\.venv\Scripts\python.exe tools\check_package.py dist\BentCorner.exe
if ($LASTEXITCODE -ne 0) { throw "Verbotene Dateien im fertigen Paket (DirectML/Qt Timeline/VirtualKeyboard) – nicht verteilen" }

Write-Host ""
Write-Host "Fertig: dist\BentCorner.exe"
Write-Host "Beim ersten Start fragt das Programm, wo die Daten liegen sollen."
