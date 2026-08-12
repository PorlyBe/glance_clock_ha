"""Name resolution for notices.

Every value a notice carries is an integer on the wire and a friendly name in
the service call. Those used to be looked up with a default, so a colour the
palette does not have arrived as white, an unknown animation as a pulse, and a
misspelled sound as silence -- all three indistinguishable from the clock
ignoring the command. These tests pin the loud version.

The indices asserted here are the firmware's own, read from const.py, so a
change to the tables that silently shifted a value would fail here rather than
on the wall.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"


def _load_notice():
    """Load services/notice.py without importing the package, which needs Home Assistant."""
    package = types.ModuleType("_glance")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_glance"] = package

    utils = types.ModuleType("_glance.utils")
    utils.__path__ = [str(COMPONENT / "utils")]
    sys.modules["_glance.utils"] = utils

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

    exceptions = types.ModuleType("homeassistant.exceptions")
    exceptions.ServiceValidationError = type("ServiceValidationError", (Exception,), {})
    sys.modules["homeassistant.exceptions"] = exceptions

    def _load(name: str, path: Path):
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    const = _load("_glance.const", COMPONENT / "const.py")
    _load("_glance.utils.enums", COMPONENT / "utils" / "enums.py")
    _load("_glance.utils.led_utils", COMPONENT / "utils" / "led_utils.py")
    module = _load("_glance.services.notice", COMPONENT / "services" / "notice.py")
    return module, const


# Held onto here rather than imported inside a test: every test file in this
# suite builds its own "_glance" package in sys.modules, and whichever imports
# last wins. The reference survives that; a later import would not.
notice, const = _load_notice()
resolve_notice = notice.resolve_notice


def test_the_defaults_are_the_ones_that_were_always_sent():
    # An empty call has to keep producing the same frame as before, or every
    # existing automation that relies on the defaults changes behaviour.
    assert resolve_notice({}) == {
        "animation": 1,  # pulse
        "sound": 0,  # none
        "color": 12,  # white
        "priority": 16,  # medium
        "text_modifier": 0,  # none
    }


def test_names_resolve_to_the_firmware_indices():
    resolved = resolve_notice(
        {
            "animation": "thunderstorm",
            "sound": "bells",
            "color": "sky_blue",
            "priority": "critical",
            "text_modifier": "rapid",
        }
    )
    assert resolved == {
        "animation": 16,
        "sound": 6,
        "color": 17,
        "priority": 80,
        "text_modifier": 2,
    }


def test_names_survive_the_whitespace_a_template_leaves_behind():
    # A multiline Jinja block keeps the indentation on each branch, which is
    # how colours arrive from a real automation.
    assert resolve_notice({"color": "  Sky_Blue\n"})["color"] == 17


@pytest.mark.parametrize(
    "alias, real",
    [("green", "lime_green"), ("purple", "indigo"), ("orange", "dark_orange"), ("cyan", "aqua")],
)
def test_the_colour_aliases_work_in_a_notice_too(alias, real):
    # The palette has none of these four -- the first names anyone reaches for.
    # They resolve for set_leds, and somebody who learned that will write them
    # in a notice; failing there only would be a difference with no reason.
    assert resolve_notice({"color": alias})["color"] == const.COLORS[real]


def test_raw_indices_still_pass_through():
    # The service used to take integers, and send_command-style calls still do.
    assert resolve_notice({"animation": 11, "color": 5})["animation"] == 11
    assert resolve_notice({"animation": 11, "color": 5})["color"] == 5


@pytest.mark.parametrize(
    "field, value",
    [
        ("animation", "sparkle"),
        ("sound", "trumpet"),
        ("color", "chartreuse"),
        ("priority", "urgent"),
        ("text_modifier", "bounce"),
    ],
)
def test_unknown_names_raise_rather_than_defaulting(field, value):
    with pytest.raises(ValueError) as err:
        resolve_notice({field: value})
    assert value in str(err.value)


def test_the_error_lists_what_would_have_worked():
    # The whole point of raising: the message has to answer "then what?"
    with pytest.raises(ValueError) as err:
        resolve_notice({"color": "chartreuse"})
    message = str(err.value)
    assert "sky_blue" in message and "lawn_green" in message


def test_every_animation_the_service_offers_resolves():
    # services.yaml is generated from these tables; if a dropdown option could
    # not resolve, the UI would offer a value the service rejects.
    for field, table in (
        ("animation", const.ANIMATIONS),
        ("sound", const.SOUNDS),
        ("color", const.COLORS),
        ("priority", const.PRIORITIES),
        ("text_modifier", const.TEXT_MODIFIERS),
    ):
        for name, index in table.items():
            assert resolve_notice({field: name})[field] == index
