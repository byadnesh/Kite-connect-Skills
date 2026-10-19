"""Import a skill's `scripts.<module>` in isolation.

Every skill has its own top-level `scripts` package, so tests purge `scripts*` from
sys.modules before importing from a different skill.
"""

import importlib
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"

# Keep caches/journals out of the real home directory during tests.
os.environ.setdefault("KITE_SKILLS_HOME", tempfile.mkdtemp(prefix="kite-skills-test-"))


def load(skill: str, module: str):
    for name in list(sys.modules):
        if name == "scripts" or name.startswith("scripts."):
            del sys.modules[name]
    # Modules insert their own skill root into sys.path; drop every skill root so only `skill` is visible.
    sys.path[:] = [p for p in sys.path if Path(p).resolve().parent != SKILLS.resolve()]
    importlib.invalidate_caches()
    root = str(SKILLS / skill)
    sys.path.insert(0, root)
    try:
        return importlib.import_module(f"scripts.{module}")
    finally:
        if root in sys.path:
            sys.path.remove(root)
