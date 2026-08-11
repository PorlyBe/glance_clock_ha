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


ANIMATION_SWEEP = led_utils.ANIMATION_SWEEP
GIF_ANIMATIONS = led_utils.GIF_ANIMATIONS
check_speed = led_utils.check_speed
resolve_animation = led_utils.resolve_animation


def test_the_frame_that_ran_fire_in_red() -> None:
    """Full ring, all four rings deep, red -- verified on hardware."""
    assert pack_segment(0, "red", length=48, ring=0, rings_tall=4) == 388864


def test_the_purple_fire_matches_the_schema_default() -> None:
    """The first attempt rendered nothing because the colour defaulted to black.

    The schema's own default carries BlueViolet, which is why substituting it
    made the animation appear.
    """
    assert pack_segment(0, "blue_violet", length=48, ring=0, rings_tall=4) == 782080
    assert pack_segment(0, "black", length=48, ring=0, rings_tall=4) >> 16 == 0


def test_every_firmware_animation_has_a_type() -> None:
    assert GIF_ANIMATIONS == {
        "fire": 10, "wheel": 11, "flower": 12, "flower2": 13,
        "fan": 14, "sun": 15, "thunderstorm": 16, "cloud": 17,
    }


def test_animation_names_are_validated() -> None:
    assert resolve_animation("Fire") == "fire"
    assert resolve_animation("sweep") == ANIMATION_SWEEP
    with pytest.raises(ValueError, match="unknown animation"):
        resolve_animation("explosion")


def test_only_the_sweep_accepts_a_direction() -> None:
    assert check_speed(ANIMATION_SWEEP, -3) == -3
    assert check_speed("fire", 10) == 10
    with pytest.raises(ValueError, match="only 'sweep' uses negative"):
        check_speed("fire", -3)
    with pytest.raises(ValueError, match="sweep speed"):
        check_speed(ANIMATION_SWEEP, 11)


scene_steps_from_config = led_utils.scene_steps_from_config
FRAMES_PER_SECOND = led_utils.FRAMES_PER_SECOND


def test_steps_chain_onto_each_other_by_default() -> None:
    steps = scene_steps_from_config(
        [
            {"frames": 25, "segments": [{"start": 0, "color": "red"}]},
            {"frames": 25, "segments": [{"start": 6, "color": "red"}]},
            {"frames": 10, "segments": [{"start": 12, "color": "red"}]},
        ]
    )
    assert [(s["at"], s["frames"]) for s in steps] == [(0, 25), (25, 25), (50, 10)]


def test_an_explicit_start_frame_wins_and_moves_the_cursor() -> None:
    steps = scene_steps_from_config(
        [
            {"frames": 25, "segments": [{"start": 0, "color": "red"}]},
            {"at": 100, "frames": 25, "segments": [{"start": 6, "color": "red"}]},
            {"frames": 25, "segments": [{"start": 12, "color": "red"}]},
        ]
    )
    assert [s["at"] for s in steps] == [0, 100, 125]


def test_seconds_convert_to_frames() -> None:
    steps = scene_steps_from_config([{"seconds": 0.5, "segments": [{"start": 0, "color": "red"}]}])
    assert steps[0]["frames"] == FRAMES_PER_SECOND // 2


def test_a_single_area_step_can_be_written_flat() -> None:
    """Nesting a one-item list inside every step is needless ceremony."""
    flat = scene_steps_from_config([{"start": 3, "color": "lime", "frames": 5}])
    nested = scene_steps_from_config(
        [{"frames": 5, "segments": [{"start": 3, "color": "lime"}]}]
    )
    assert flat == nested


def test_the_chase_that_ran_on_hardware() -> None:
    """Eight steps, each erasing the previous block -- a single block moved."""
    steps = scene_steps_from_config(
        [
            {
                "seconds": 0.5,
                "segments": [
                    {"start": ((i - 1) % 8) * 6, "length": 6, "rings_tall": 4, "color": "black"},
                    {"start": i * 6, "length": 6, "rings_tall": 4, "color": "red"},
                ],
            }
            for i in range(8)
        ]
    )
    assert len(steps) == 8
    assert steps[-1]["at"] + steps[-1]["frames"] == 200  # four seconds
    assert steps[1]["segments"][1] == pack_segment(6, "red", length=6, rings_tall=4)


def test_empty_and_malformed_scenes_are_rejected() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        scene_steps_from_config([])
    with pytest.raises(ValueError, match="frames must be at least 1"):
        scene_steps_from_config([{"frames": 0, "segments": [{"start": 0, "color": "red"}]}])
    with pytest.raises(ValueError, match="cannot be negative"):
        scene_steps_from_config([{"at": -1, "segments": [{"start": 0, "color": "red"}]}])
