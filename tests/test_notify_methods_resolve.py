"""Every `self.something()` in the notification service has a definition.

notify.py is the largest file in the integration and the one most often edited
by search-and-replace. A call to a method that no longer exists compiles
cleanly, imports cleanly, and passes every other test in this suite -- it fails
only when the clock is actually asked to do the thing, which is the worst place
to find out.

That happened once: removing the slot-clearing took the refresh helper with it,
because the two sat next to each other. Four call sites were left pointing at
nothing.
"""

import ast
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"
NOTIFY = COMPONENT / "notify.py"


def _service_class() -> ast.ClassDef:
    tree = ast.parse(NOTIFY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "GlanceClockNotificationService":
            return node
    pytest.fail("GlanceClockNotificationService is gone from notify.py")


def _defined_methods(cls: ast.ClassDef) -> set[str]:
    return {
        node.name
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _called_on_self(cls: ast.ClassDef) -> set[str]:
    calls = set()
    for node in ast.walk(cls):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            calls.add(func.attr)
    return calls


def test_every_self_call_has_a_method_behind_it():
    cls = _service_class()
    defined = _defined_methods(cls)
    called = _called_on_self(cls)

    # Attributes that are set rather than defined, or inherited from
    # BaseNotificationService. Anything else must be a method on the class.
    inherited = {"hass"}

    missing = sorted(called - defined - inherited)
    assert not missing, (
        "these are called on self but defined nowhere in the class: "
        + ", ".join(missing)
    )


def test_the_refresh_helper_is_still_there():
    # Named on its own because it is the one that went missing, and because
    # every scene write depends on it to appear without a fifteen second wait.
    cls = _service_class()
    assert "_refresh_scene_playback" in _defined_methods(cls)
    assert "_refresh_scene_playback" in _called_on_self(cls)


def test_the_slot_clearing_is_gone():
    # Verified on hardware: a scene written to an occupied slot replaces it and
    # shows at once, so clearing first was a command spent on nothing.
    source = NOTIFY.read_text(encoding="utf-8")
    assert "_free_scene_slot" not in source
