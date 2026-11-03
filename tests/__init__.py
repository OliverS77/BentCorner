"""Tests never touch the user's real data: BC_HOME points to a fresh temp folder (removed at the end) before anything
reads the data folder (system.datahome decides on import) – so `import app` and every module that reads settings.json
or writes caches only ever see this folder. And tests run in English (tr() texts are compared literally)."""
import atexit
import os
import shutil
import tempfile

_HOME = tempfile.mkdtemp(prefix="bentcorner-tests-")
os.environ["BC_HOME"] = _HOME   # always – also when a BC_HOME of the developer is set
atexit.register(shutil.rmtree, _HOME, True)

from system import i18n  # noqa: E402

i18n.set_language("en")
