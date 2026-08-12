"""Frame building for the raw command service.

The service exists so undocumented parts of the firmware can be reached without
another release, which makes its guard rails the part worth testing: a frame
that is malformed reaches the clock as some other command entirely, and two
commands would take the clock away from its owner for good.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"


def _load_raw():
    """Load services/raw.py without importing the package, which needs Home Assistant."""
    package = types.ModuleType("_glance")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_glance"] = package

    const = types.ModuleType("_glance.const")
    const.DOMAIN = "glance_clock"
    sys.modules["_glance.const"] = const

    services = types.ModuleType("_glance.services")
    services.__path__ = [str(COMPONENT / "services")]
    sys.modules["_glance.services"] = services

    ha = types.ModuleType("homeassistant")
    ha.__path__ = []
    sys.modules["homeassistant"] = ha

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.ServiceCall = object
    sys.modules["homeassistant.core"] = core

    entries = types.ModuleType("homeassistant.config_entries")
    entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = entries

    spec = importlib.util.spec_from_file_location(
        "_glance.services.raw", COMPONENT / "services" / "raw.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_glance.services.raw"] = module
    spec.loader.exec_module(module)
    return module


raw = _load_raw()


def test_frame_is_always_four_bytes_before_the_payload():
    # Every frame observed working on hardware carries a full four byte header,
    # so a command with no modifiers still pads rather than sending one byte.
    assert raw.build_frame(31, None, None) == bytes([31, 0, 0, 0])


def test_modifiers_fill_from_the_left_and_pad_with_zeroes():
    assert raw.build_frame(0, [8, 2], None) == bytes([0, 8, 2, 0])


def test_a_bare_integer_is_accepted_as_a_single_modifier():
    assert raw.build_frame(5, 1, None) == bytes([5, 1, 0, 0])


def test_payload_hex_is_accepted_in_the_forms_a_human_would_type():
    expected = bytes([5, 0, 0, 0, 0x20, 0x01])
    for written in ("2001", "20 01", "20:01", "0x2001"):
        assert raw.build_frame(5, None, written) == expected


def test_payload_may_be_given_as_a_list_of_bytes():
    assert raw.build_frame(5, None, [0x20, 0x01]) == bytes([5, 0, 0, 0, 0x20, 0x01])


@pytest.mark.parametrize("command", sorted(raw.BLOCKED_COMMANDS))
def test_the_commands_that_cannot_be_undone_are_refused(command):
    # Clearing the bonds unpairs a clock that has no pairing button, and
    # clearing user info wipes what the dead cloud service cannot restore.
    with pytest.raises(ValueError, match="blocked"):
        raw.build_frame(command, None, None)


def test_more_than_three_modifiers_is_refused_rather_than_truncated():
    # Silently dropping the fourth byte would send a different command than
    # the one asked for.
    with pytest.raises(ValueError, match="at most"):
        raw.build_frame(0, [1, 2, 3, 4], None)


@pytest.mark.parametrize("command", [-1, 256])
def test_a_command_outside_one_byte_is_refused(command):
    with pytest.raises(ValueError, match="0-255"):
        raw.build_frame(command, None, None)


def test_a_modifier_outside_one_byte_is_refused():
    with pytest.raises(ValueError, match="0-255"):
        raw.build_frame(0, [300], None)


def test_odd_length_hex_is_refused_rather_than_guessed_at():
    with pytest.raises(ValueError, match="even number"):
        raw.build_frame(5, None, "201")


def test_non_hex_payload_is_refused():
    with pytest.raises(ValueError, match="not valid hex"):
        raw.build_frame(5, None, "zzzz")
