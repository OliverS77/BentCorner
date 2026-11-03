"""Camera image controls (focus, exposure, gain, sharpness …) via the driver's DirectShow interfaces.

Also works while the image comes through Media Foundation: the values live in the device itself. Webcams often forget
them after unplugging/restarting – so the app saves them per camera and re-applies them on start.
"""
import logging
from ctypes import POINTER, c_long

log = logging.getLogger("booster")

# (key, label, interface, property) – interface "cam" = IAMCameraControl, "amp" = IAMVideoProcAmp
PROPS = [("focus", "Fokus", "cam", 6), ("exposure", "Belichtung", "cam", 4), ("gain", "Verstärkung", "amp", 9),
         ("brightness", "Helligkeit", "amp", 0), ("contrast", "Kontrast", "amp", 1), ("sharpness", "Schärfe", "amp", 4),
         ("saturation", "Sättigung", "amp", 3), ("white", "Weißabgleich", "amp", 7), ("zoom", "Zoom", "cam", 3),
         ("backlight", "Gegenlicht-Ausgleich", "amp", 8)]
AUTO, MANUAL = 1, 2  # flags of the driver interface

_ifaces = None


def _interfaces():
    global _ifaces
    if _ifaces is None:
        from comtypes import COMMETHOD, GUID, HRESULT, IUnknown
        methods = [
            COMMETHOD([], HRESULT, "GetRange", (["in"], c_long, "p"), (["out"], POINTER(c_long), "mn"),
                      (["out"], POINTER(c_long), "mx"), (["out"], POINTER(c_long), "step"),
                      (["out"], POINTER(c_long), "default"), (["out"], POINTER(c_long), "caps")),
            COMMETHOD([], HRESULT, "Set", (["in"], c_long, "p"), (["in"], c_long, "v"), (["in"], c_long, "flags")),
            COMMETHOD([], HRESULT, "Get", (["in"], c_long, "p"), (["out"], POINTER(c_long), "v"),
                      (["out"], POINTER(c_long), "flags")),
        ]

        class IAMCameraControl(IUnknown):
            _iid_ = GUID("{C6E13370-30AC-11d0-A18C-00A0C9118956}")
            _methods_ = methods

        class IAMVideoProcAmp(IUnknown):
            _iid_ = GUID("{C6E13360-30AC-11d0-A18C-00A0C9118956}")
            _methods_ = methods
        _ifaces = {"cam": IAMCameraControl, "amp": IAMVideoProcAmp}
    return _ifaces


# COM objects (comtypes/pygrabber) must never become garbage: pygrabber's graphs hold reference cycles, so they are
# freed by the garbage collector – in whatever thread it happens to run (the recognizer's), not the one that made them,
# and a COM Release from another thread crashes the program (a tester's access violation, 0.9.2). Whatever is done
# with goes in here and stays until the program ends (comtypes skips the Release while shutting down) – a few KB.
_KEEP = []


def keep(*objs):
    """Done with these COM objects: keep them alive (never garbage, never released in a foreign thread)."""
    _KEEP.extend(o for o in objs if o is not None)


class Controls:
    """Controls of one camera (index as in the DirectShow camera list). Use only in the main thread. Values read
    once and kept (the dialog's rebuilds asked the camera every time – a 4K camera blocked the window)."""

    def __init__(self, index):
        import comtypes
        comtypes.CoInitialize()
        from pygrabber.dshow_graph import FilterGraph
        self._graph = FilterGraph()  # keep the camera's filter alive
        self._graph.add_video_input_device(index)
        flt = self._graph.get_input_device().instance
        self._if, self._vals = {}, {}
        for key, cls in _interfaces().items():
            try:
                self._if[key] = flt.QueryInterface(cls)
            except Exception:
                pass
        self.ranges = {}
        for key, _, iface, prop in PROPS:
            ctl = self._if.get(iface)
            if ctl is None:
                continue
            try:
                mn, mx, step, default, caps = ctl.GetRange(prop)
                if mx > mn:
                    self.ranges[key] = {"min": mn, "max": mx, "step": max(1, step), "default": default,
                                        "auto": bool(caps & AUTO), "manual": bool(caps & MANUAL)}
            except Exception:
                pass

    def _ctl(self, key):
        iface, prop = next((i, p) for k, _, i, p in PROPS if k == key)
        return self._if[iface], prop

    def get(self, key):
        """-> (value, automatic?) – read from the camera once, then from what was set"""
        if key not in self._vals:
            ctl, prop = self._ctl(key)
            v, flags = ctl.Get(prop)
            self._vals[key] = (v, bool(flags & AUTO))
        return self._vals[key]

    def set(self, key, value, auto=False):
        ctl, prop = self._ctl(key)
        r = self.ranges[key]
        value = max(r["min"], min(r["max"], int(value)))
        ctl.Set(prop, value, AUTO if auto and r["auto"] else MANUAL)
        self._vals[key] = (value, bool(auto and r["auto"]))

    def close(self):
        """Done with this camera's controls: its COM objects into the keep (main thread, never garbage)."""
        keep(self._graph, *self._if.values())
        self._graph, self._if, self.ranges = None, {}, {}

    def reset(self):
        for key, r in self.ranges.items():
            try:
                self.set(key, r["default"], auto=r["auto"])
            except Exception as e:
                log.info("Camera controls %s: %s", key, e)

    def apply(self, saved):
        """Apply saved values {key: [value, auto]}."""
        for key, (value, auto) in (saved or {}).items():
            if key in self.ranges:
                try:
                    self.set(key, value, auto)
                except Exception as e:
                    log.info("Camera controls %s: %s", key, e)

    def snapshot(self):
        out = {}
        for key in self.ranges:
            try:
                v, a = self.get(key)
                out[key] = [v, a]
            except Exception:
                pass
        return out


def open_controls(index):
    """Controls or None (camera without controls, e.g. virtual cameras)."""
    try:
        c = Controls(index)
        return c if c.ranges else None
    except Exception as e:
        log.info("Camera controls: %s", e)
        return None
