# Backlog: GPU-Beschleuniger unter Linux (nur Planung, Stand 31.10.2026)

Grundsatz (seit 0.9.7.4, `scanner/accel.py`): CPU ist überall die Grundlage, dazu nur der Beschleuniger, den das
System selbst mitbringt. Wir liefern **keine** proprietäre GPU-Bibliothek mit (Signatur/Open Source):
Windows → DirectML aus Windows (ab 1.15.0), Mac → CoreML (im normalen onnxruntime), Linux → CPU.

## Linux-Installer: „GPU-Beschleuniger zusätzlich installieren?“

**Start (erste Linux-Version):** nur ein Hinweis mit Link zur Hersteller-Seite. Wir laden nichts, wir liefern nichts mit.

**Später, als Option – Download auf Wunsch (Auflagen von legal):**
- Standard „Nein“; vorher Name, Größe, Quelle und Lizenz-Link anzeigen.
- Die Lizenz (EULA) bestätigt der Nutzer selbst beim Hersteller/Paketmanager.
- Bevorzugt über den Paketmanager der Distribution – keine nachgebauten NVIDIA-URLs.
- sudo vorher ankündigen und den Deinstallationsweg nennen.
- Keine Treiber installieren.
- Ein Schritt im Installer, kein Pop-up.
- Ohne Beschleuniger läuft alles auf der CPU weiter.

**Technik:**
- Keine `nvidia-*`-pip-Pakete und keine CUDA-/cuDNN-Bibliotheken ins Paket; nur die System-Installation nutzen
  (onnxruntime-gpu findet CUDA aus dem System).
- OpenVINO (Intel, Apache-2.0) darf laut legal mitgeliefert werden – erst messen (Tempo, Größe, Fingerabdrücke müssen
  zum Index passen: Prüfstand `tools/scan-bench`, 0 falsch).
- WebGPU (`onnxruntime-ep-webgpu`, MIT, Vulkan) als herstellerneutraler Weg, sobald es aus der Beta ist – messen.
- Die Weiche in `scanner/accel.py` bekommt dafür einen Linux-Zweig; `fingerprint` misst weiter GPU gegen CPU und nimmt
  das Schnellere.
- Signatur unter Linux: GPG bzw. Store – nicht die Windows-Zertifikate.
