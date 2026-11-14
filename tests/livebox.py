"""For tests about the LIVE box (what a Ship build does): since the DEV split (Oliver/Gordon/lead 13.11.2026,
net/boxbase.py) the source without BC_SYNC_BASE talks to the gated test instance. These modules check the mailbox,
forget, vault and gate logic of the live case with simulated HTTP, so they pin the address to the live server – as a
Ship build does. A local box (BC_SYNC + BC_SYNC_BASE) still wins. The DEV case itself: tests/test_dev_build.py.

    from tests import livebox
    setUpModule, tearDownModule = livebox.module()
"""
from unittest import mock


def _live(settings=None):
    """The address as the live code had it before the split: a local box, else the mailbox address in the settings
    (these tests point it at their fake box), else the live server."""
    from collection import syncrun
    from system import contacts
    stored = ((settings or {}).get("relay") or {}).get("url") if isinstance(settings, dict) else None
    return (syncrun.test_base() or stored or contacts.SERVER).rstrip("/")


def module():
    p = mock.patch("net.boxbase.base", _live)
    return p.start, p.stop
