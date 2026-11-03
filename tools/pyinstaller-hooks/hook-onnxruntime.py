# Replaces the onnxruntime hook of pyinstaller-hooks-contrib (build.ps1: --additional-hooks-dir): the same provider
# libraries from onnxruntime/capi, but WITHOUT DirectML.dll. The app uses the DirectML from Windows itself
# (System32, scanner/accel.py) – we ship no proprietary GPU library (signing/open source, 0.9.7.4).
# build.ps1 checks afterwards that no DirectML*.dll ended up in the exe in any other way.
import os

from PyInstaller.utils.hooks import collect_dynamic_libs

binaries = [(src, dest) for src, dest in collect_dynamic_libs("onnxruntime")
            if not os.path.basename(src).lower().startswith("directml")]
