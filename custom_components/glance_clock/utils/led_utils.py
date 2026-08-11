"""Packing for the LED ring segments used by CustomScene fills.

The clock has four concentric rings of 48 LEDs. A lit area is described by a
single 22-bit integer, laid out in Glance.proto as:

        5  4      3  2      1
    000000 00 000000 00 000000

    1 start pixel   0-47, clockwise, pixel 0 at twelve o'clock
    2 ring          0-3, counted from the outer edge
    3 length        stored one less than the real pixel count
    4 height        stored one less than the number of rings covered
    5 colour        index into the Color enum

Verified against hardware: pixel 0 is at twelve o'clock and numbering runs
clockwise, ring 0 is the outermost, and all four fields render as described.
"""

from __future__ import annotations

from ..const import COLORS

RING_COUNT = 4
PIXELS_PER_RING = 48

#: Third byte of a CustomScene command.
DISPLAY_MODES = {
    # Scene owns the display; the digital clockface is hidden while it shows.
    "exclusive": 0,
    # Scene sits on the watchface, shown at the same time as the digital time.
    "watchface": 8,
    # Scene joins the rotation, alternating with the clockface every ~15s.
    "ring_and_text": 24,
}

#: Object.method values.
METHOD_FILL = 2
METHOD_MOVING_BAR = 5
METHOD_GIF = 8

#: Animations built into the firmware, drawn as a GIF object. They are
#: single-colour patterns tinted by the colour in the segment -- a colour of 0
#: is black, which renders nothing at all.
GIF_ANIMATIONS = {
    "fire": 10,
    "wheel": 11,
    "flower": 12,
    "flower2": 13,
    "fan": 14,
    "sun": 15,
    "thunderstorm": 16,
    "cloud": 17,
}

#: A sweep that fills the area from its start pixel, pauses, and repeats.
#: Not a GIF -- it is a MovingBar, and its speed carries the direction.
ANIMATION_SWEEP = "sweep"

ANIMATIONS = (ANIMATION_SWEEP, *GIF_ANIMATIONS)

#: Lengths that are not a multiple of 8 are rounded down by the clock itself.
GIF_LENGTH_MULTIPLE = 8


def resolve_color(color) -> int:
    """Accept either a colour name from COLORS or a raw palette index."""
    if isinstance(color, str):
        key = color.strip().lower()
        if key not in COLORS:
            raise ValueError(
                f"unknown colour '{color}'; expected one of {', '.join(sorted(COLORS))}"
            )
        return COLORS[key]

    index = int(color)
    if not 0 <= index <= 0x3F:
        raise ValueError("colour index must be 0-63")
    return index


def pack_segment(
    start: int,
    color,
    length: int = 1,
    ring: int = 0,
    rings_tall: int = 1,
) -> int:
    """Pack one lit area into the clock's segment integer.

    `length` and `rings_tall` are real counts. The wire format stores one less
    than each, which is an easy off-by-one to inherit from the documentation.
    """
    start = int(start)
    length = int(length)
    ring = int(ring)
    rings_tall = int(rings_tall)

    if not 0 <= start < PIXELS_PER_RING:
        raise ValueError(f"start must be 0-{PIXELS_PER_RING - 1}, got {start}")
    if not 1 <= length <= PIXELS_PER_RING:
        raise ValueError(f"length must be 1-{PIXELS_PER_RING}, got {length}")
    if not 0 <= ring < RING_COUNT:
        raise ValueError(f"ring must be 0-{RING_COUNT - 1}, got {ring}")
    if not 1 <= rings_tall <= RING_COUNT:
        raise ValueError(f"rings_tall must be 1-{RING_COUNT}, got {rings_tall}")
    if ring + rings_tall > RING_COUNT:
        raise ValueError(
            f"ring {ring} with {rings_tall} rings of height runs past the "
            f"{RING_COUNT} available rings; the clock rejects this"
        )

    return (
        (start & 0x3F)
        | ((ring & 0x03) << 6)
        | (((length - 1) & 0x3F) << 8)
        | (((rings_tall - 1) & 0x03) << 14)
        | ((resolve_color(color) & 0x3F) << 16)
    )


def segments_from_config(items: list[dict]) -> list[int]:
    """Turn the service's list of dicts into packed segments."""
    if not items:
        raise ValueError("at least one segment is required")

    packed = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"segment {index} must be a mapping, got {type(item).__name__}")
        if "start" not in item or "color" not in item:
            raise ValueError(f"segment {index} needs at least 'start' and 'color'")
        packed.append(
            pack_segment(
                item["start"],
                item["color"],
                length=item.get("length", 1),
                ring=item.get("ring", 0),
                rings_tall=item.get("rings_tall", 1),
            )
        )
    return packed


#: The clock plays scenes at this rate, so all times are in fiftieths.
FRAMES_PER_SECOND = 50


def scene_steps_from_config(
    items: list[dict],
    default_frames: int = 25,
) -> list[dict]:
    """Normalise a list of animation steps into frame-timed fills.

    Each step may give `at` (the frame it starts on) and either `frames` or
    `seconds` for how long it runs. Omitting `at` chains the step onto the end
    of the previous one, which is what you want almost every time.

    Anything drawn stays on screen after its step ends -- the clock does not
    clear between frames -- so a step that should erase something has to paint
    over it.
    """
    if not items:
        raise ValueError("a scene needs at least one step")

    steps: list[dict] = []
    cursor = 0

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"step {index} must be a mapping, got {type(item).__name__}")

        frames = item.get("frames")
        if frames is None and "seconds" in item:
            frames = round(float(item["seconds"]) * FRAMES_PER_SECOND)
        frames = int(default_frames if frames is None else frames)
        if frames < 1:
            raise ValueError(f"step {index}: frames must be at least 1")

        at = cursor if item.get("at") is None else int(item["at"])
        if at < 0:
            raise ValueError(f"step {index}: 'at' cannot be negative")

        segments = item.get("segments")
        if segments is None and "start" in item:
            # A step with a single area can be written flat, without nesting a
            # one-item list inside it.
            segments = [item]

        steps.append(
            {
                "at": at,
                "frames": frames,
                "segments": segments_from_config(segments or []),
            }
        )
        cursor = at + frames

    return steps


def resolve_animation(name) -> str:
    """Validate an animation name."""
    key = str(name).strip().lower()
    if key not in ANIMATIONS:
        raise ValueError(
            f"unknown animation '{name}'; expected one of {', '.join(sorted(ANIMATIONS))}"
        )
    return key


def check_speed(animation: str, speed: int) -> int:
    """Range-check speed, which means different things per animation.

    A sweep takes -10 to 10, where the sign is the direction. The firmware
    animations take 0 to 10 and have no direction, so a negative value there is
    a mistake worth naming rather than silently clamping.
    """
    speed = int(speed)
    if animation == ANIMATION_SWEEP:
        if not -10 <= speed <= 10:
            raise ValueError("sweep speed must be -10 to 10")
    elif not 0 <= speed <= 10:
        raise ValueError(
            f"'{animation}' speed must be 0-10; only 'sweep' uses negative "
            "values, where the sign reverses direction"
        )
    return speed


def resolve_mode(mode) -> int:
    """Accept a display mode name or its raw value."""
    if isinstance(mode, str):
        key = mode.strip().lower()
        if key not in DISPLAY_MODES:
            raise ValueError(
                f"unknown display mode '{mode}'; expected one of "
                f"{', '.join(sorted(DISPLAY_MODES))}"
            )
        return DISPLAY_MODES[key]

    value = int(mode)
    if not 0 <= value <= 255:
        raise ValueError("display mode must be 0-255")
    return value
