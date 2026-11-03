# Shaders (Qt Quick ShaderEffect)

| Source | Compiled (checked in) | Used by |
|---|---|---|
| `loadcard.frag` | `loadcard.frag.qsb` | `components/Loading.qml` – the loading card (logo card, fold, glint) |

Qt 6 only loads shaders that are precompiled as `.qsb`. The compiler `qsb` is part of **PySide6-Addons**, which is
not in the app's venv. So it lives in its own tool venv, outside the repo and outside the build – in the BentCorner
folder next to `dev` (run from there):

```
<python 3.12> -m venv tools\qsb-venv
tools\qsb-venv\Scripts\python -m pip install pyside6-addons==6.11.2
```

The version must match PySide6 in `requirements.txt` (currently 6.11.2).

After changing a `.frag` (in the project folder):

```
.venv\Scripts\python tools\compile_shaders.py
```

This writes `<name>.frag.qsb` (GLSL 100 es/120/150, HLSL 50, MSL 12) and `<name>.frag.sha256`, the checksum of the
source. **Check in all three files.** `tests/test_shaders.py` fails if a `.frag` was changed without compiling again.
