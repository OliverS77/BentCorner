#!/usr/bin/env bash
# Baut dist/BentCorner.app
#   chmod +x build_mac.sh && ./build_mac.sh
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -q -r requirements.txt pyinstaller

# Fingerabdruck-Index aller Karten mitliefern (tools/build_fingerprints.py erzeugt ihn in data/fp_build)
if [ -f data/fp_build/fingerprints-all.npz ]; then
    cp -f data/fp_build/fingerprints-all.npz models/fingerprints-all.npz
else
    echo "Hinweis: kein Fingerabdruck-Index aller Karten (tools/build_fingerprints.py) - nur geladene Sets."
fi

# Programmsymbol aus dem Logo-Paket brand/logo (icon.icns, da macOS - siehe ui/iconkit.py); ohne brand/ ein Platzhalter
if [ -d brand/logo ]; then
    .venv/bin/python -m ui.iconkit && ICON=brand/icon.icns && BRAND=(--add-data "brand:brand")
else
    .venv/bin/python -m ui.iconkit build/icon.icns && ICON=build/icon.icns && BRAND=()
fi

.venv/bin/pyinstaller --noconfirm --clean --windowed \
    --name BentCorner --icon "$ICON" \
    --exclude-module tkinter \
    --add-data "setliste.json:." \
    --add-data "THIRD_PARTY_NOTICES.md:." \
    --add-data "LICENSE:." \
    --add-data "LICENSE-ASSETS.md:." \
    --add-data "fonts:fonts" \
    --add-data "assets:assets" \
    "${BRAND[@]}" \
    --add-data "models:models" \
    --add-data "qml:qml" \
    --collect-all rapidocr_onnxruntime \
    --collect-binaries onnxruntime \
    --collect-submodules games --collect-submodules scanner --collect-submodules cards \
    --collect-submodules collection --collect-submodules net --collect-submodules ui --collect-submodules system \
    app.py

# Kamera-Berechtigung: ohne NSCameraUsageDescription fragt macOS nie nach Zugriff, sondern blockt ihn stumm.
/usr/libexec/PlistBuddy -c "Add :NSCameraUsageDescription string 'Bent°Corner braucht die Kamera, um Karten zu scannen.'" \
    dist/BentCorner.app/Contents/Info.plist
# Info.plist nach dem Patch neu signieren - sonst "Info.plist=not bound" und macOS ignoriert den Eintrag oben
codesign --force --deep --sign - dist/BentCorner.app

echo ""
echo "Fertig: dist/BentCorner.app"
echo "Beim ersten Start fragt macOS wegen eines fehlenden Entwickler-Zertifikats nach - Rechtsklick auf die App ->"
echo "\"Öffnen\" (statt Doppelklick) umgeht das; danach startet sie auch per Doppelklick normal."
echo "Das Programm fragt dann, wo die Daten liegen sollen."
