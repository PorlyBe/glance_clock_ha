"""Which degree symbol the forecast puts on the clock.

Home Assistant converts a weather entity's temperatures to the user's own unit
before the integration ever sees them, so the numbers are already correct and
converting again would double-convert. Only the letter has to be chosen, and
choosing it wrongly mislabels a whole day of temperatures.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"


def _load_forecast():
    """Load services/forecast.py without Home Assistant installed."""
    package = types.ModuleType("_gf")
    package.__path__ = [str(COMPONENT)]
    sys.modules["_gf"] = package

    const = types.ModuleType("_gf.const")
    const.DOMAIN = "glance_clock"
    sys.modules["_gf.const"] = const

    utils = types.ModuleType("_gf.utils")
    utils.__path__ = [str(COMPONENT / "utils")]
    sys.modules["_gf.utils"] = utils

    colour = types.ModuleType("_gf.utils.color_utils")
    colour.parse_color_input = lambda *a, **k: 0
    colour.interpolate_color = lambda *a, **k: 0
    sys.modules["_gf.utils.color_utils"] = colour

    services = types.ModuleType("_gf.services")
    services.__path__ = [str(COMPONENT / "services")]
    sys.modules["_gf.services"] = services

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
        "_gf.services.forecast", COMPONENT / "services" / "forecast.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_gf.services.forecast"] = module
    spec.loader.exec_module(module)
    return module


forecast = _load_forecast()


def _unit(entity_unit, system_unit=None):
    state = types.SimpleNamespace(attributes={"temperature_unit": entity_unit})
    hass = types.SimpleNamespace(
        config=types.SimpleNamespace(
            units=types.SimpleNamespace(temperature_unit=system_unit)
        )
    )
    return forecast._temperature_unit(hass, state)


@pytest.mark.parametrize("written", ["°C", "C", "°c"])
def test_celsius_is_recognised_however_the_entity_writes_it(written):
    assert _unit(written) == "C"


@pytest.mark.parametrize("written", ["°F", "F", "°f"])
def test_fahrenheit_is_recognised_however_the_entity_writes_it(written):
    assert _unit(written) == "F"


def test_the_entity_wins_over_the_system_setting():
    # A single entity can override the system unit, and the label has to follow
    # the numbers actually being sent.
    assert _unit("°F", system_unit="°C") == "F"


def test_the_system_setting_is_used_when_the_entity_says_nothing():
    assert _unit(None, system_unit="°F") == "F"


def test_celsius_is_the_fallback_when_nothing_says_otherwise():
    # Guessing Fahrenheit for a clock that has never been sold outside metric
    # markets would mislabel far more often than the reverse.
    assert _unit(None, system_unit=None) == "C"


def test_a_missing_state_does_not_raise():
    hass = types.SimpleNamespace(
        config=types.SimpleNamespace(
            units=types.SimpleNamespace(temperature_unit="°F")
        )
    )
    assert forecast._temperature_unit(hass, None) == "F"
