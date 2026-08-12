"""The flags the clock pushes on scene_state.

Decoded on hardware 2026-08-12 by moving the DND window across the current
time and toggling mute, watching glance_clock_notification. The frames below
are the ones that actually arrived, so these tests pin the observation rather
than restate the constants:

    04 22   nothing suppressed
    14 22   the quiet window is in force
    0c 22   muted

Night mode and brightness changes pushed nothing at all, which is why neither
has a bit here to test.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"


def _load_flags():
    """Load the bit definitions without importing Home Assistant's entity stack."""
    source = (COMPONENT / "binary_sensor.py").read_text(encoding="utf-8")
    namespace: dict = {}
    for line in source.splitlines():
        if line.startswith(("IDLE_BIT", "DIGITAL_CLOCK_BIT", "DND_BIT", "MUTE_BIT")):
            exec(line, namespace)  # noqa: S102 -- four constant assignments
    return namespace


flags = _load_flags()

#: The exact frames observed, as the event carried them.
NOTHING_SUPPRESSED = [0x04, 0x22]
QUIET_WINDOW = [0x14, 0x22]
MUTED = [0x0C, 0x22]


def test_the_quiet_window_frame_reads_as_dnd():
    assert QUIET_WINDOW[0] & flags["DND_BIT"]


def test_the_idle_frame_does_not():
    assert not NOTHING_SUPPRESSED[0] & flags["DND_BIT"]


def test_the_muted_frame_reads_as_muted():
    assert MUTED[0] & flags["MUTE_BIT"]


def test_dnd_and_mute_are_separate_bits():
    # They were toggled independently on hardware and moved independently, so
    # a decoder that conflated them would have looked right in one test.
    assert not MUTED[0] & flags["DND_BIT"]
    assert not QUIET_WINDOW[0] & flags["MUTE_BIT"]


def test_the_flags_do_not_collide_with_the_display_bits():
    # scene_state and scene_data are different characteristics, but both are
    # decoded from a first byte in the same module, and mixing them up would
    # produce a sensor that is subtly wrong rather than obviously broken.
    assert not flags["DND_BIT"] & flags["IDLE_BIT"]
    assert not flags["MUTE_BIT"] & flags["IDLE_BIT"]
    assert not flags["DND_BIT"] & flags["DIGITAL_CLOCK_BIT"]
    assert not flags["MUTE_BIT"] & flags["DIGITAL_CLOCK_BIT"]


@pytest.mark.parametrize("frame", [NOTHING_SUPPRESSED, QUIET_WINDOW, MUTED])
def test_bit_two_is_set_in_every_frame_seen(frame):
    # Unexplained, and recorded rather than decoded: it was set in all three
    # samples. If a frame ever arrives without it, this test is the note
    # saying that used to be true.
    assert frame[0] & 0x04


@pytest.mark.parametrize("frame", [NOTHING_SUPPRESSED, QUIET_WINDOW, MUTED])
def test_the_second_byte_has_never_moved(frame):
    assert frame[1] == 0x22
