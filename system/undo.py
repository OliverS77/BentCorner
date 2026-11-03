"""Undo / Redo for the whole program (the last 5 steps).

Every data store (collection, decks, wishlist, lists, friends) reports here before it writes its file
(before_write). We remember the old content; whatever is written in quick succession (one action often saves
several files) is one step. undo() writes the old state back and remembers the current one for redo().
Afterwards the program has to re-read the data (app.after_undo). Silent saves (e.g. new prices) are not a
step: with quiet(): …

The running session is not included (while scanning, "U" = take back the last card).
"""
import contextlib
import pathlib
import time

MAX = 5            # this many steps back
GROUP_S = 2.0      # writes within this interval belong to one step

_steps, _redo = [], []
_quiet = 0
_cleared = [""]    # why the history was emptied last ("game": a game switch) – until the next step


@contextlib.contextmanager
def quiet():
    """Save without an Undo step (prices updated, the restore itself …)."""
    global _quiet
    _quiet += 1
    try:
        yield
    finally:
        _quiet -= 1


def _read(path):
    try:
        return path.read_text("utf-8") if path.exists() else None
    except OSError:
        return False   # not readable: better not to record a step


LAST_WRITE = [0.0]   # time of the last change to personal data (for the automatic backup)


def before_write(path, label=""):
    """path is about to be written – remember the old content (once per step and file)."""
    LAST_WRITE[0] = time.time()
    if _quiet:
        return
    path = pathlib.Path(path)
    old = _read(path)
    if old is False:
        return
    now = time.monotonic()
    if _steps and now - _steps[-1]["t"] < GROUP_S:
        st = _steps[-1]
        st["t"] = now
    else:
        st = {"t": now, "files": {}, "label": label}
        _steps.append(st)
        del _steps[:-MAX]
    st["files"].setdefault(str(path), old)
    _cleared[0] = ""
    if label and not st.get("label"):
        st["label"] = label
    _redo.clear()


def _swap(src, dst):
    st = src.pop()
    back = {"t": 0.0, "files": {}, "label": st.get("label", "")}
    for p, text in st["files"].items():
        path = pathlib.Path(p)
        cur = _read(path)
        back["files"][p] = None if cur is False else cur
        try:
            if text is None:
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(path.suffix + ".undo")
                tmp.write_text(text, "utf-8")
                tmp.replace(path)
        except OSError:
            pass
    dst.append(back)
    del dst[:-MAX]
    return [pathlib.Path(p) for p in st["files"]], st.get("label", "")


def undo():
    """Undo the last step -> (changed files, label) or None."""
    return _swap(_steps, _redo) if _steps else None


def redo():
    """Redo an undone step -> (changed files, label) or None."""
    return _swap(_redo, _steps) if _redo else None


def clear(why=""):
    """Empty the history. why: "game" (a game switch – Ctrl+Z then says so) or ""."""
    _steps.clear()
    _redo.clear()
    _cleared[0] = why


def cleared_why():
    """Why there is nothing to undo ("game") – "" once a new step came."""
    return _cleared[0]
