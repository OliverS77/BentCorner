"""Foreign text on screen – only as text (review 08.11.: T3/H2-3 low rest, lead 10.11.).

Names of friends, devices and trade partners arrive from the mailbox, sync, tickets and files. They are kept exactly as
they came (sync, matching and comparisons stay the same) – only what is SHOWN is cleaned:
- name(s): for display – no control characters, at most n characters, and nothing in it can turn a label into rich
  text: < > become ‹ › and an entity like "&amp;" stays visible as typed.
- rich(html): the safety net of every rich-text label and toast – only our own tags pass, never a remote image (it
  would load on display), no event attributes; anything else shows as text.
- looks_rich(s): whether a label is rich text by itself – only our own tags or an entity count ("x <3 y" stays text).
"""
import html as _html
import re

OWN = ("b", "i", "u", "s", "em", "strong", "br", "span", "font", "a", "img", "p", "div", "table", "tr", "td", "th",
       "small", "big", "sub", "sup", "ul", "ol", "li", "h1", "h2", "h3", "h4", "hr", "center", "tt", "code", "pre",
       "nobr")
_OWN_TAG = re.compile(r"</?(?:" + "|".join(OWN) + r")(?=[\s/>])[^<>]*>", re.I)
_ENTITY = re.compile(r"&(#\d+|#x[0-9a-f]+|[a-z]+);", re.I)
_ANY_TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9]*)([^<>]*)>")
_EVENT_ATTR = re.compile(r"""\s+on[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""", re.I)
_SRC = re.compile(r"""\ssrc\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))""", re.I)
_LOCAL = ("file:", "data:", "qrc:", "image:")
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f​-‏‪-‮⁦-⁩]")


def name(s, n=60):
    """A foreign name as it may be shown: plain text in any label, the stored value untouched."""
    t = " ".join(_CTRL.sub("", str(s or "")).split())
    if len(t) > n:
        t = t[:n - 1].rstrip() + "…"
    t = t.replace("<", "‹").replace(">", "›")
    return _ENTITY.sub(lambda m: "&⁠" + m.group(1) + ";", t)   # "&amp;" stays visible as typed, never decoded


def looks_rich(s):
    return bool(_OWN_TAG.search(s) or _ENTITY.search(s))


def rich(h):
    """Rich text with only our own tags: unknown tags as visible text, no remote images, no on…= attributes."""
    def tag(m):
        close, t, rest = m.group(1), m.group(2).lower(), m.group(3)
        if t not in OWN:
            return _html.escape(m.group(0))
        rest = _EVENT_ATTR.sub("", rest)
        if t == "img" and not close:
            src = _SRC.search(rest)
            url = (src.group(2) or src.group(3) or src.group(4) or "") if src else ""
            if not url.strip().lower().startswith(_LOCAL):
                return ""   # a remote image would load on display (a beacon): never
        return f"<{close}{m.group(2)}{rest}>"
    return _ANY_TAG.sub(tag, str(h or ""))
