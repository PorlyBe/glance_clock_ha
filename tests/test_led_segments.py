"""LED ring segment packing.

The expected values here are the exact frames that were written to a real clock
and photographed, so they pin the layout rather than restate it.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

# led_utils uses a relative import for the colour table, so it needs to load as
# part of a package -- but the real package's __init__ pulls in Home Assistant.
# Build the two package levels by hand so the module under test stays runnable
# without a Home Assistant install.
_COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_pkg = types.ModuleType("_glance")
_pkg.__path__ = [str(_COMPONENT)]
sys.modules["_glance"] = _pkg

_utils = types.ModuleType("_glance.utils")
_utils.__path__ = [str(_COMPONENT / "utils")]
sys.modules["_glance.utils"] = _utils

_load("_glance.const", _COMPONENT / "const.py")
led_utils = _load("_glance.utils.led_utils", _COMPONENT / "utils" / "led_utils.py")

DISPLAY_MODES = led_utils.DISPLAY_MODES
pack_segment = led_utils.pack_segment
resolve_color = led_utils.resolve_color
resolve_mode = led_utils.resolve_mode
segments_from_config = led_utils.segments_from_config


def test_the_frame_that_lit_a_quarter_of_the_outer_ring() -> None:
    """Twelve red pixels from twelve o'clock, verified on hardware."""
    assert pack_segment(0, "red", length=12, ring=0) == 0x050B00


def test_field_layout_round_trips() -> None:
    value = pack_segment(24, "sky_blue", length=6, ring=2, rings_tall=2)
    assert value & 0x3F == 24  # start
    assert (value >> 6) & 0x03 == 2  # ring
    assert ((value >> 8) & 0x3F) + 1 == 6  # length
    assert ((value >> 14) & 0x03) + 1 == 2  # rings tall
    assert (value >> 16) & 0x3F == resolve_color("sky_blue")


def test_length_and_height_are_stored_one_less() -> None:
    """The off-by-one the wire format invites."""
    assert (pack_segment(0, "white", length=1) >> 8) & 0x3F == 0
    assert (pack_segment(0, "white", length=48) >> 8) & 0x3F == 47
    assert (pack_segment(0, "white", rings_tall=1) >> 14) & 0x03 == 0
    assert (pack_segment(0, "white", rings_tall=4) >> 14) & 0x03 == 3


def test_rings_are_addressed_independently() -> None:
    """Four arcs at the same position on different rings rendered concentrically."""
    stacked = [pack_segment(0, "red", length=6, ring=r) for r in range(4)]
    assert [(v >> 6) & 0x03 for v in stacked] == [0, 1, 2, 3]
    assert len(set(stacked)) == 4


def test_height_beyond_the_available_rings_is_rejected() -> None:
    with pytest.raises(ValueError, match="runs past"):
        pack_segment(0, "red", ring=2, rings_tall=3)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start": 48},
        {"start": -1},
        {"start": 0, "length": 0},
        {"start": 0, "length": 49},
        {"start": 0, "ring": 4},
        {"start": 0, "rings_tall": 0},
    ],
)
def test_out_of_range_geometry_is_rejected(kwargs) -> None:
    kwargs.setdefault("start", 0)
    with pytest.raises(ValueError):
        pack_segment(color="red", **kwargs)


def test_unknown_colour_names_are_rejected_by_name() -> None:
    with pytest.raises(ValueError, match="unknown colour"):
        pack_segment(0, "chartreuse")


def test_colours_accept_names_and_indices() -> None:
    assert resolve_color("red") == 5
    assert resolve_color("RED") == 5
    assert resolve_color(5) == 5


def test_display_modes_match_the_values_verified_on_hardware() -> None:
    """watchface showed the scene and the digital time at once; 24 alternated."""
    assert DISPLAY_MODES == {"exclusive": 0, "watchface": 8, "ring_and_text": 24}
    assert resolve_mode("watchface") == 8
    assert resolve_mode(24) == 24


def test_segments_from_config_applies_defaults() -> None:
    packed = segments_from_config([{"start": 3, "color": "lime"}])
    assert packed == [pack_segment(3, "lime", length=1, ring=0, rings_tall=1)]


def test_segments_from_config_rejects_incomplete_entries() -> None:
    with pytest.raises(ValueError, match="needs at least"):
        segments_from_config([{"start": 0}])
    with pytest.raises(ValueError, match="at least one segment"):
        segments_from_config([])
