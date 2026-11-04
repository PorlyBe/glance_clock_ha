"""Load pure app modules without starting HA or importing its integration entry point."""

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for name, path in (
    ("custom_components", ROOT / "custom_components"),
    ("custom_components.glance_clock", ROOT / "custom_components/glance_clock"),
):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module

sys.modules["custom_components"].glance_clock = sys.modules[
    "custom_components.glance_clock"
]
