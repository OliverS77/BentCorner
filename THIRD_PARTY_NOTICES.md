# Komponenten und Inhalte Dritter


Das Programm und dieses Repository enthalten folgende Komponenten Dritter. Sie gehören nicht zu Bent°Corner und
behalten ihre eigenen Lizenzen. Der Quellcode von Bent°Corner selbst steht unter der GPL-3.0 mit Zusatzbedingungen
nach § 7 (`LICENSE`); Marken-Assets in `brand/` sind ausgenommen (`brand/BRAND.md`).

Direkt im Repository liegen davon nur die Schriften in `fonts/` (mit `OFL-Inter.txt`, `OFL-Barlow.txt` bzw.
`OFL-Noto.txt`). Das Bildmodell DINOv2-small lädt `build.ps1` beim Bauen von Hugging Face (gepackte und
fp16-Fassung, feste Version, Prüfsumme); beide Fassungen stecken im Programm. Die Bibliotheken
werden über `requirements.txt` (feste Versionen) installiert und beim Bauen in die .exe gepackt. Diese Datei,
`LICENSE`, `LICENSE-ASSETS.md` und `brand/BRAND.md` liegen dem Programm bei (Einstellungen → Rechtliches & Daten → Hinweise zu
Drittanbietern). Die vollständigen Lizenztexte liegen im Programmordner unter `licenses/`.

## Programmbibliotheken (in der .exe)

| Komponente | Version | Lizenz (SPDX) | Quelle |
|---|---|---|---|
| Qt (The Qt Company), über PySide6-Essentials | 6.11.2 | LGPL-3.0-only ¹ | https://www.qt.io/ · https://code.qt.io/ |
| PySide6 / Shiboken6 (Qt for Python) | 6.11.2 | LGPL-3.0-only ¹ | https://pyside.org · https://code.qt.io/cgit/pyside/pyside-setup.git |
| Mesa llvmpipe (`opengl32sw.dll`, Software-OpenGL von Qt), darin LLVM 3.6.2 | 11.2.2 | MIT (LLVM 3.6.2: NCSA); Texte `licenses/Mesa-LICENSE.txt`, `licenses/LLVM-3.6.2-LICENSE.txt` | https://mesa3d.org/ · https://llvm.org/ |
| Python (Python Software Foundation) | 3.12.10 | PSF-2.0 ² | https://www.python.org/ |
| OpenSSL (`libssl-3.dll`, `libcrypto-3.dll`, von Python) | 3.0.16 | Apache-2.0 | https://www.openssl.org/ |
| SQLite (`sqlite3.dll`) | 3.49.1 | blessing (Public Domain) | https://sqlite.org/ |
| libffi (`libffi-8.dll`) | 3.4.x (Version nicht ausgelesen) | MIT | https://sourceware.org/libffi/ |
| OpenCV (opencv-python) | 4.14.0 (Paket 4.14.0.94) | Apache-2.0 ³ | https://opencv.org/ · https://github.com/opencv/opencv-python |
| FFmpeg (`cv2/opencv_videoio_ffmpeg4140_64.dll`, mit libvpx und libaom) | 7.1 (libavcodec 61.19.100) | LGPL-2.1-or-later (libvpx, libaom: BSD) ⁴ | https://ffmpeg.org/ · https://github.com/opencv/opencv_3rdparty/tree/ffmpeg/4.x |
| NumPy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | https://numpy.org/ |
| OpenBLAS (in NumPy, mit LAPACK und GCC-Laufzeit) | 0.3.34 | BSD-3-Clause; LAPACK: BSD-3-Clause-Open-MPI; GCC-Laufzeit: GPL-3.0-or-later WITH GCC-exception-3.1 | https://www.openblas.net/ |
| ONNX Runtime (Microsoft), Paket onnxruntime-directml | 1.24.4 | MIT ⁵ | https://github.com/microsoft/onnxruntime |
| RapidOCR (rapidocr-onnxruntime) | 1.4.4 | Apache-2.0 | https://github.com/RapidAI/RapidOCR |
| PaddleOCR-Modelle (PP-OCR, Baidu/PaddlePaddle), als ONNX über RapidOCR | – | Apache-2.0 | https://github.com/PaddlePaddle/PaddleOCR |
| RapidFuzz | 3.14.6 | MIT | https://github.com/rapidfuzz/RapidFuzz |
| Pillow (inkl. FreeType, HarfBuzz, lcms2, libjpeg-turbo, libpng, libtiff, libwebp, OpenJPEG, libavif, zlib, xz) | 12.3.0 | MIT-CMU (+ Lizenzen der Bibliotheken, z. B. FTL, IJG, Libpng, libtiff, BSD-3-Clause, Zlib) | https://python-pillow.github.io/ |
| Shapely | 2.1.2 | BSD-3-Clause | https://github.com/shapely/shapely |
| GEOS (in Shapely, `geos.dll`, `geos_c.dll`) | 3.13.1 | LGPL-2.1-or-later ⁴ | https://libgeos.org/ |
| pyclipper (mit Clipper von Angus Johnson) | 1.4.0 | MIT (Clipper: BSL-1.0) | https://github.com/fonttools/pyclipper |
| PyYAML | 6.0.3 | MIT | https://pyyaml.org/ |
| requests | 2.34.2 | Apache-2.0 | https://github.com/psf/requests |
| urllib3 | 2.8.0 | MIT | https://github.com/urllib3/urllib3 |
| idna | 3.20 | BSD-3-Clause | https://github.com/kjd/idna |
| charset-normalizer | 3.5.1 | MIT | https://github.com/jawah/charset_normalizer |
| certifi (Mozilla-Zertifikatsliste) | 2026.10.23 | MPL-2.0 ⁶ | https://github.com/certifi/python-certifi |
| cryptography (mit OpenSSL, statisch) | 50.0.2 (OpenSSL 4.0.3) | Apache-2.0 OR BSD-3-Clause (OpenSSL: Apache-2.0) | https://github.com/pyca/cryptography |
| PyNaCl / libsodium (Verschlüsselung) | 1.5.0 | Apache-2.0 / ISC | https://github.com/pyca/pynacl · https://libsodium.org |
| cffi (nur `_cffi_backend`) | 2.1.1 | MIT-0 | https://github.com/python-cffi/cffi |
| segno (QR-Code) | 1.6.6 | BSD-3-Clause | https://github.com/heuer/segno |
| pygrabber | 0.2 | MIT | https://github.com/andreaschiavinato/python_grabber |
| comtypes | 1.4.17 | MIT | https://github.com/enthought/comtypes |
| cv2-enumerate-cameras | 1.4.0 | MIT | https://github.com/lukehugh/cv2_enumerate_cameras |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging |
| setuptools (mitgezogen beim Bauen, inkl. importlib_metadata, zipp, jaraco.*, more_itertools, tomli, wheel, backports.tarfile) ⁷ | 84.0.0 | MIT | https://github.com/pypa/setuptools |
| Microsoft Visual C++ Laufzeit (`vcruntime140*.dll`, `msvcp140*.dll`) | 14.40–14.51 | Microsoft Visual C++ Redistributable („Distributable Code“, unverändert weitergegeben) | https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist |
| PyInstaller (Bootloader) | 6.22.3 | GPL-2.0-or-later WITH Bootloader-exception | https://pyinstaller.org/ |

## Modelle und Schriften

| Komponente | Lizenz (SPDX) | Quelle |
|---|---|---|
| DINOv2-small (Meta AI), ONNX-Export von Xenova (`dinov2-small-q.onnx` gepackt, `dinov2-small-fp16.onnx`) | Apache-2.0 | https://huggingface.co/Xenova/dinov2-small · https://github.com/facebookresearch/dinov2 |
| Schrift Inter (Rasmus Andersson) | OFL-1.1 | https://rsms.me/inter/ |
| Schrift Barlow Semi Condensed (Jeremy Tribby) | OFL-1.1 | https://github.com/jpt/barlow |
| Schrift BC Symbols – Teilmenge aus Noto Sans Symbols, Noto Sans Symbols 2 und Noto Sans Math, © 2022 The Noto Project Authors / Google LLC (`BCSymbols-Regular.ttf`, gebaut mit `tools/make_symbol_font.py`) | OFL-1.1 | https://github.com/notofonts/symbols · https://github.com/notofonts/math |

## Anmerkungen

¹ **Qt/PySide6 unter LGPL-3.0:** Qt und PySide6 liegen als eigene, austauschbare DLL-Dateien im Programmordner
(`PySide6\Qt6*.dll`, `shiboken6\`); sie sind nicht statisch eingebunden. Wer möchte, kann sie durch eine selbst
gebaute, kompatible Fassung derselben Version ersetzen. Der Quellcode von Qt 6.11.2 und PySide6 6.11.2 steht unter
https://download.qt.io/official_releases/qt/6.11/6.11.2/ und https://download.qt.io/official_releases/QtForPython/ bereit;
auf Anfrage schicken wir ihn auch selbst, mindestens drei Jahre nach der letzten Weitergabe dieser Version (Kontakt
siehe „Rechtliches“). Der Text der LGPL-3.0 (und der GPL-3.0, auf der sie aufbaut) liegt unter `licenses/`.
Qt-Module, die es frei nur unter der GPL gibt (Qt Quick Timeline, Qt Virtual Keyboard), sind seit 0.9.7.5 nicht im
Programm; der Bau bricht ab, falls sie hineingeraten.
Qt enthält selbst Code Dritter (u. a. HarfBuzz, FreeType, libpng, libjpeg, PCRE2, zlib, double-conversion, md4c);
die Liste steht unter https://doc.qt.io/qt-6/licenses-used-in-qt.html.

² **Python** bringt eigene Bestandteile Dritter mit (u. a. expat, zlib, bzip2, xz/liblzma, mpdecimal, OpenSSL,
SQLite, libffi); ihre Hinweise stehen im Python-Lizenztext (`licenses/Python-LICENSE.txt`).

³ **OpenCV** enthält statisch u. a. libjpeg-turbo, libpng/libspng, libtiff, libwebp, OpenJPEG, OpenEXR, zlib,
Protocol Buffers, FlatBuffers, quirc und Intel IPP ICV (Intel Simplified Software License). Alle Texte stehen in
`licenses/opencv-LICENSE-3RD-PARTY.txt` (aus dem opencv-python-Paket).

⁴ **FFmpeg und GEOS unter LGPL-2.1:** beide liegen als eigene DLL im Programmordner
(`cv2\opencv_videoio_ffmpeg4140_64.dll`, `Shapely.libs\geos*.dll`) und können ersetzt werden. Das FFmpeg ist ohne
GPL- und „nonfree“-Teile gebaut; OpenH264 von Cisco wird nicht mitgeliefert. Quellcode: FFmpeg
https://ffmpeg.org/download.html (Bauskripte: https://github.com/opencv/opencv_3rdparty/tree/ffmpeg/4.x), GEOS
https://libgeos.org/usage/download/; auf Anfrage schicken wir ihn auch selbst, mindestens drei Jahre nach der letzten
Weitergabe dieser Version. Text der LGPL-2.1 unter `licenses/`.

⁵ **ONNX Runtime** enthält Code Dritter; die Hinweise stehen in `licenses/onnxruntime-ThirdPartyNotices.txt`.

⁶ **certifi** (MPL-2.0): unverändert weitergegeben; Quellcode unter der genannten Adresse.

⁷ **setuptools** wird von PyInstaller mit eingepackt, Bent°Corner nutzt es nicht selbst.

## Frühere Versionen

Frühere Versionen: 0.9.4 und 0.9.5 enthielten zusätzlich OpenSSL 3 (libcrypto-3-x64.dll, libssl-3-x64.dll;
Apache-2.0, https://www.openssl.org/) aus Git for Windows. Versionen 0.9.0–0.9.3 können dieselben Dateien enthalten
haben. Bis 0.9.7.3 enthielt das Programm außerdem DirectML (Microsoft).

## Daten, die das Programm zur Laufzeit lädt

- **Magic-Kartendaten und -bilder:** über die [Scryfall-API](https://scryfall.com/docs/api). Nutzung gemäß den
  Scryfall-Richtlinien; die Daten werden nicht hinter einer Bezahlschranke angeboten. Der Erkennungs-Index im
  Magic-Datenpaket ist aus Scryfall-Bildern berechnet (enthält keine Bilder).
- **Pokémon-Kartendaten und -bilder:** [TCGdex](https://tcgdex.dev/) (Daten unter MIT-Lizenz, © 2021 TCGdex, Text
  unten). Die Datenbank liegt im Pokémon-Datenpaket; die Bilder kommen über den Bild-Spiegel des Bent°Corner-Servers.
  Einzelne englische Kartenbilder, die TCGdex nicht hat, wurden einmalig von
  [pokemontcg.io](https://pokemontcg.io/) geholt und kommen ebenfalls über den Bild-Spiegel.
- **Yu-Gi-Oh!:** siehe Abschnitt „Yu-Gi-Oh!“ unten.
- **Preise:** Magic: Cardmarket-Trend und TCGplayer aus den Scryfall-Bulk-Daten. Pokémon: Cardmarket (öffentliche
  Preis-Tagesdatei, lädt die App selbst) und TCGplayer über den Bent°Corner-Preisserver (Daten von
  [TCGCSV](https://tcgcsv.com/)). Yu-Gi-Oh!: Bent°Corner-Preisserver (Cardmarket über
  [YGOPRODeck](https://ygoprodeck.com/), TCGplayer über TCGCSV). Alle Preise sind Richtwerte ohne Gewähr.
- **Kombos, Turnierdaten, Beliebtheit:** [Commander Spellbook](https://commanderspellbook.com/) (Code MIT),
  [EDHTop16](https://edhtop16.com/); der EDHREC-Rang stammt aus den Scryfall-Daten (die App fragt EDHREC nicht ab).
- **Preisverlauf:** [MTGJSON](https://mtgjson.com/), MIT-Lizenz:

  > MIT License · Copyright (c) 2018-Present Zach Halpern
  >
  > Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
  > documentation files (the "Software"), to deal in the Software without restriction, including without limitation
  > the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
  > to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above
  > copyright notice and this permission notice shall be included in all copies or substantial portions of the
  > Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
  > LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
  > SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
  > OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
  > DEALINGS IN THE SOFTWARE.
- **Wechselkurse:** Referenzkurse der Europäischen Zentralbank (Quelle: EZB), abgerufen über
  [Frankfurter](https://frankfurter.dev/) (Open-Source-API).
- **Farbpalette der Kartenrückseiten:** die 16 Farben (und 16 Zusatzfarben) der Palette von
  [PICO-8](https://www.lexaloffle.com/pico-8.php) (Lexaloffle Games) – nur die Farbwerte, kein Code und keine Inhalte
  aus PICO-8.

Regeln der Dienste (Abstände, Pflicht-Angaben, Bildrichtlinien) stehen in `net/netpolite.py`.

### TCGdex – MIT-Lizenz

  > MIT License · Copyright (c) 2021 TCGdex
  >
  > Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
  > documentation files (the "Software"), to deal in the Software without restriction, including without limitation
  > the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and
  > to permit persons to whom the Software is furnished to do so, subject to the following conditions: The above
  > copyright notice and this permission notice shall be included in all copies or substantial portions of the
  > Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
  > LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
  > SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
  > OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
  > DEALINGS IN THE SOFTWARE.

Jedes Datenpaket enthält zusätzlich eine `LICENSES.txt` mit den Quellen und Lizenzen seiner Daten.

## Yu-Gi-Oh!

- **Kartendaten und -bilder:** [YGOPRODeck](https://ygoprodeck.com/) ([API-Regeln](https://ygoprodeck.com/api-guide/)).
  Die Datenbank liegt im Yu-Gi-Oh!-Datenpaket; die Bilder wurden einmal geladen und werden vom Bent°Corner-Server
  selbst gehostet, wie YGOPRODeck es verlangt. Die App fragt YGOPRODeck nicht direkt ab.
- **Drucke aus Japan, Korea, Asien und Spanien, Namen in weiteren Sprachen:** aus
  [YGOJSON](https://github.com/iconmaster5326/YGOJSON) (Code unter MIT-Lizenz, © 2024 iconmaster). Diese Daten
  stammen aus [Yugipedia](https://yugipedia.com/) und stehen unter
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/deed.de). Seit Version 0.9.4 liegen sie als eigene,
  offen lesbare Datei `ygo-locale.sqlite` im Yu-Gi-Oh!-Datenpaket (Auswahl und Umwandlung durch Bent°Corner) und
  werden erst auf deinem Gerät mit der Kartendatenbank zusammengeführt. Für diese Datei gilt CC BY-SA 4.0; die
  übrigen Daten und Bent°Corner selbst stehen nicht unter dieser Lizenz. Für diese Drucke gibt es keine erlaubte
  Bildquelle – die App zeigt das englische Kartenbild mit dem Hinweis „Bild: englischer Druck“.
- **Preise:** Cardmarket über YGOPRODeck, TCGplayer über [TCGCSV](https://tcgcsv.com/) – über den
  Bent°Corner-Preisserver.

Yu-Gi-Oh! ist eine Marke von Konami Digital Entertainment; Kartentexte und -bilder © 4K Media Inc. / Konami.
Bent°Corner steht in keiner Verbindung zu Konami oder 4K Media.

## Disney Lorcana

- **Kartendaten:** [LorcanaJSON](https://lorcanajson.org/). **Kartenbilder:** von Ravensburger
  (api.lorcana.ravensburger.com), über den Bild-Spiegel des Bent°Corner-Servers.
- **Preise:** Cardmarket (öffentliche Preis-Tagesdatei, lädt die App selbst) und TCGplayer über den
  Bent°Corner-Preisserver (Daten von [TCGCSV](https://tcgcsv.com/)).

Uses trademarks and/or copyrights associated with Disney Lorcana TCG, used under Ravensburger's
[Community Code Policy](https://cdn.ravensburger.com/lorcana/community-code-en). We are expressly prohibited from
charging you to use or access this content. Bent°Corner is not published, endorsed, or specifically approved by
Disney or Ravensburger.

## Pokémon

Pokémon, Kartennamen und -bilder sind Eigentum von Nintendo, Creatures Inc., GAME FREAK inc. und The Pokémon Company.
Bent°Corner wird von Nintendo und The Pokémon Company weder hergestellt noch unterstützt oder gefördert und ist mit
ihnen nicht verbunden.

## Magic: The Gathering

Bent°Corner is unofficial Fan Content permitted under the Fan Content Policy. Not approved/endorsed by Wizards.
Portions of the materials used are property of Wizards of the Coast. ©Wizards of the Coast LLC.
(https://company.wizards.com/en/legal/fancontentpolicy)
Magic: The Gathering, Kartennamen, Kartenbilder und Set-Symbole sind Eigentum von Wizards of the Coast.

## Marken (Sammelhinweis)

Alle genannten Marken, Spielnamen, Kartennamen und Kartenbilder gehören ihren jeweiligen Inhabern. Bent°Corner ist
ein unabhängiges, kostenloses Fan-Projekt und steht in keiner Verbindung zu Wizards of the Coast, The Pokémon
Company, Nintendo, Creatures, GAME FREAK, Konami, 4K Media, Disney oder Ravensburger. „Bent°Corner“ und „SCAN°“ sind
Namen dieses Projekts und nicht Teil der Lizenzen (siehe `LICENSE` § 7(e) und `brand/BRAND.md`).
