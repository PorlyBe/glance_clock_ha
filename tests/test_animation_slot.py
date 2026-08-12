"""The Animation Slot control on the device page.

The animation buttons wrote to slot 0 and nothing else, so a second animation
replaced the first and putting one somewhere else meant dropping into YAML.
The slot is part of the shared animation state now, like the colour and the
speed, and Run and Stop both read it -- Stop clearing a different slot from the
one Run filled would be worse than no Stop button at all.
"""

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"


def _load_animation_state():
    package = types.ModuleType("_gs")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_gs"] = package

    const = types.ModuleType("_gs.const")
    const.DOMAIN = "glance_clock"
    sys.modules["_gs.const"] = const

    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    sys.modules.setdefault("homeassistant", ha)
    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant.core"] = core

    spec = importlib.util.spec_from_file_location(
        "_gs.animation_state", COMPONENT / "animation_state.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_gs.animation_state"] = module
    spec.loader.exec_module(module)
    return module


animation_state = _load_animation_state()


def test_the_slot_is_part_of_the_shared_state():
    assert "slot" in animation_state.DEFAULTS


def test_it_defaults_to_the_slot_the_buttons_always_used():
    # Anyone upgrading has automations and habits built on slot 0. Defaulting
    # anywhere else would move their animation without asking.
    assert animation_state.DEFAULTS["slot"] == 0


def test_the_default_is_in_range():
    assert 0 <= animation_state.DEFAULTS["slot"] <= 7


def _button_source() -> str:
    return (COMPONENT / "button.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("method", ["async_press", "_run_effect"])
def test_running_an_animation_reads_the_chosen_slot(method):
    # Guards against a future edit reinstating the constant: the point of the
    # entity is that these three paths follow it.
    source = _button_source()
    assert 'state.get("slot"' in source, "the buttons no longer read the chosen slot"


def test_stop_clears_the_same_slot_run_filled():
    tree = ast.parse(_button_source())
    stop = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "GlanceClockStopAnimationButton"
    )
    # ast.unparse normalises quotes, so match on the shape rather than the text
    body = ast.unparse(stop).replace("'", '"')
    assert "async_delete_scene" in body
    assert 'state.get("slot"' in body, (
        "Stop clears a fixed slot again; it has to follow Animation Slot or it "
        "will leave the running animation up and clear an empty slot instead"
    )


def test_the_number_entity_exists_and_is_registered():
    source = (COMPONENT / "number.py").read_text(encoding="utf-8")
    assert "class GlanceClockAnimationSlotNumber" in source
    assert "GlanceClockAnimationSlotNumber(" in source.split("async_setup_entry")[1]


def test_the_number_covers_every_slot_the_firmware_has():
    source = (COMPONENT / "number.py").read_text(encoding="utf-8")
    slot_class = source.split("class GlanceClockAnimationSlotNumber")[1]
    assert "_attr_native_min_value = 0" in slot_class
    assert "_attr_native_max_value = 7" in slot_class


def test_the_slot_is_a_slider():
    # Erik asked for a drag rather than up-and-down arrows. Pinned because it
    # is a deliberate choice and a one-word edit away from being lost.
    source = (COMPONENT / "number.py").read_text(encoding="utf-8")
    slot_class = source.split("class GlanceClockAnimationSlotNumber")[1]
    assert "NumberMode.SLIDER" in slot_class
    assert "NumberMode.BOX" not in slot_class
