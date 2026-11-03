"""Parts that may be missing: the public source (tools/public/export_public.py) leaves out the server (its own
repository) and the private data tools – the tests for them skip instead of failing.

    from tests.optional_games import needs_server, needs_private_tools
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# The server tests load these files directly. A leftover server/ with only __pycache__ (after the move to the separate
# repository, 2026-11-01) must not count – so look for the real .py files, not just the folder.
SERVER_FILES = ("box/box.py", "prices/prices.py")


def server_present(root=ROOT):
    return all((root / "server" / f).is_file() for f in SERVER_FILES)


def server_code(root=ROOT):
    """Real files under server/ (no __pycache__, no .pyc) – what the guard in test_public_manifest looks for."""
    base = root / "server"
    return sorted(str(p.relative_to(base)) for p in base.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc") if base.is_dir() else []


needs_server = unittest.skipUnless(server_present(), "the server is not part of this source")
needs_private_tools = unittest.skipUnless((ROOT / "tools" / "owner.py").exists(), "private tools are not part of this source")
