from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from custom_components.glance_clock.apps.scenes import (
    CLEAR,
    Meeting,
    Segment,
    calendar_segments,
    clock_text,
    parse_events,
    scene_packet,
)
from custom_components.glance_clock.glance_pb2 import CustomScene

TZ = ZoneInfo("America/Detroit")
NOW = datetime(2026, 10, 14, 12, tzinfo=TZ)


def event(key="a", hour=13, end=15, color=15):
    return Meeting(key, key, NOW.replace(hour=hour), NOW.replace(hour=end), color)


def decode(packet):
    assert packet[:2] == b"\x00\x00" and packet[3] == 7
    return CustomScene.FromString(packet[4:])


def cells(segments):
    return {
        (c, r): s.color
        for s in segments
        for c in range(s.start, s.start + s.length)
        for r in range(s.lane, s.lane + s.height)
    }


def test_isolated_wedge_full_height():
    segments, hidden = calendar_segments([event()], NOW)
    assert segments == [Segment(4, 8, 0, 4, 15, "a")]
    assert hidden == 0


def test_overlaps_stack_and_each_color_reaches_outer_when_alone():
    segments, hidden = calendar_segments([event(), event("b", 14, 16, 11)], NOW)
    grid = cells(segments)
    assert [grid[(8, r)] for r in range(4)] == [15, 15, 11, 11]
    assert [grid[(12, r)] for r in range(4)] == [11] * 4
    assert hidden == 0


@pytest.mark.parametrize(
    "count,expected",
    [(1, [1, 1, 1, 1]), (2, [1, 1, 2, 2]), (3, [1, 1, 2, 3]), (4, [1, 2, 3, 4])],
)
def test_overlaps_share_four_bands_evenly(count, expected):
    meetings = [event(str(i), color=i + 1) for i in range(count)]
    segments, hidden = calendar_segments(meetings, NOW)
    assert [cells(segments)[(4, lane)] for lane in range(4)] == expected
    assert calendar_segments(list(reversed(meetings)), NOW)[0] == segments
    assert hidden == 0


def test_fifth_overlap_is_reported_and_order_stable():
    events = [event(str(i), color=i + 1) for i in range(5)]
    a, hidden = calendar_segments(events, NOW)
    assert hidden == 1
    assert calendar_segments(list(reversed(events)), NOW)[0] == a
    assert [cells(a)[(4, r)] for r in range(4)] == [1, 2, 3, 4]


def test_past_future_and_all_day_events_are_not_drawn():
    assert calendar_segments([event(hour=10, end=12)], NOW)[0] == []
    tomorrow = Meeting(
        "tomorrow", "x", NOW + timedelta(days=1), NOW + timedelta(days=1, hours=1), 2
    )
    assert calendar_segments([tomorrow], NOW)[0] == []
    response = {
        "calendar.a": {
            "events": [
                {"start": "2026-10-14", "end": "2026-10-15", "summary": "All day"},
                {
                    "start": "2026-10-14T17:00:00Z",
                    "end": "2026-10-14T18:00:00Z",
                    "summary": "Class",
                },
            ]
        }
    }
    events = parse_events(response, {"calendar.a": 11}, TZ)
    assert len(events) == 1
    assert cells(calendar_segments(events, NOW)[0])[(4, 0)] == 11


def test_midnight_wrap_and_dst_use_local_clock():
    now = NOW.replace(hour=23)
    meeting = Meeting(
        "m", "x", now + timedelta(minutes=30), now + timedelta(hours=2), 11
    )
    grid = cells(calendar_segments([meeting], now)[0])
    assert grid[(46, 0)] == grid[(0, 0)] == 11
    assert (4, 0) not in grid
    fallback = datetime(2026, 11, 1, 0, tzinfo=TZ)
    early = Meeting(
        "early", "x", fallback.replace(hour=1), fallback.replace(hour=1, minute=30), 15
    )
    late = Meeting(
        "late",
        "x",
        fallback.replace(hour=1, fold=1),
        fallback.replace(hour=1, minute=30, fold=1),
        2,
    )
    assert cells(calendar_segments([early, late], fallback)[0])[(4, 0)] == 15


@pytest.mark.parametrize(
    "effect,frames",
    [("breath_1", 80), ("breath_2", 160), ("dim_once", 16), ("dim_twice", 32)],
)
def test_calendar_cue_starts_with_text_and_restores(effect, frames):
    segments = calendar_segments([event()], NOW)[0]
    scene = decode(scene_packet(segments, text="Meeting", meeting="a", effect=effect))
    text = next(o for o in scene.object if o.method == 4)
    cue = next(o for o in scene.object if o.method == 7)
    assert text.startTime == cue.startTime == 0
    assert cue.lifeTime == frames
    assert len(cue.areaAnimation.area) == 8  # one quarter of the 32 LEDs
    assert list(scene.object[-1].fill.segment) == [CLEAR, segments[0].packed]
    assert scene.object[-1].startTime == frames


def test_custom_wave_and_sound():
    scene = decode(
        scene_packet([], text="Meeting starts soon", effect="wave", colors=(2, 1), sound=6)
    )
    cue = next(o for o in scene.object if o.method == 7)
    assert cue.areaAnimation.type == 1
    assert [a >> 16 for a in cue.areaAnimation.area] == [2, 1]
    assert scene.object[-1].sound == 6


def test_ascii_and_packet_limit():
    assert clock_text("Café\n Dance") == b"Cafe Dance"
    assert len(clock_text("x" * 200)) == 64
    with pytest.raises(ValueError, match="512"):
        scene_packet([Segment(c, 1, r, 1, 15) for c in range(48) for r in range(4)])
    with pytest.raises(ValueError):
        _ = Segment(0, 48, 3, 2, 15).packed


@pytest.mark.parametrize("duration", [3, 12, 30])
def test_breathing_spans_scroll_and_targets_whole_visible_wedge(duration):
    segments = calendar_segments([event()], NOW)[0]
    scene = decode(
        scene_packet(
            segments, text="Meeting", meeting="a", effect="breathing", duration=duration
        )
    )
    text = next(o for o in scene.object if o.method == 4)
    cue = next(o for o in scene.object if o.method == 7)
    pulse = cue.areaAnimation.pulse
    assert pulse.riseTime == pulse.fallTime == 100
    assert text.lifeTime == cue.lifeTime == duration * 50
    assert list(cue.areaAnimation.area) == [s.packed for s in segments]
    assert scene.object[-1].startTime == text.lifeTime


def test_breathing_includes_even_a_one_pixel_overlap_band():
    segments = [Segment(1, 1, 0, 1, 11, "a"), Segment(1, 1, 1, 3, 21, "b")]
    scene = decode(
        scene_packet(segments, text="Meeting", meeting="a", effect="breathing")
    )
    cue = next(o for o in scene.object if o.method == 7)
    assert list(cue.areaAnimation.area) == [segments[0].packed]
    assert list(scene.object[-1].fill.segment) == [CLEAR] + [s.packed for s in segments]
