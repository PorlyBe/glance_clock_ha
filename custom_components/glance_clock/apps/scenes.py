"""Calendar geometry and custom scenes, ported from the Mac prototype.

No network or HA dependencies: these render using Hypfer's documented protocol.
The clock has 48 columns, four rings and a fixed color palette (not RGB).
"""

import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime

from ..glance_pb2 import CustomScene


@dataclass(frozen=True)
class Meeting:
    key: str
    title: str
    start: datetime
    end: datetime
    color: int


@dataclass(frozen=True)
class Segment:
    start: int
    length: int
    lane: int
    height: int
    color: int
    meeting: str = ""

    @property
    def packed(self):
        if not (
            0 <= self.start < 48
            and 1 <= self.length <= 48 - self.start
            and 0 <= self.lane < 4
            and 1 <= self.height <= 4 - self.lane
            and 0 <= self.color <= 53
        ):
            raise ValueError("Invalid ring segment")
        return (
            self.start
            | self.lane << 6
            | (self.length - 1) << 8
            | (self.height - 1) << 14
            | self.color << 16
        )


CLEAR = Segment(0, 48, 0, 4, 0).packed
EFFECTS = (
    "none",
    "glow",
    "wave",
    "breathing",
    "breath_1",
    "breath_2",
    "dim_once",
    "dim_twice",
)


def calendar_segments(meetings, now):
    """Share four bands evenly; stack overlaps inward in event-start order.

    Absolute quarter-hours are converted to the clock's local timezone. During
    a DST fall-back, the nearer occurrence owns a repeated wall-clock column.
    More than four concurrent events are counted but cannot be drawn.
    """
    stamp = now.timestamp()
    events = sorted(
        (
            m
            for m in meetings
            if m.end.timestamp() > stamp
            and m.start.timestamp() < stamp + 43200
            and m.end.timestamp() > m.start.timestamp()
        ),
        key=lambda m: (m.start.timestamp(), m.key),
    )
    cells = [[None] * 48 for _ in range(4)]
    hidden, seen = set(), set()
    quarter = int(stamp // 900) * 900
    for offset in range(48):
        start = quarter + offset * 900
        local = datetime.fromtimestamp(start, now.tzinfo)
        column = local.hour % 12 * 4 + local.minute // 15
        if column in seen:
            continue
        seen.add(column)
        active = [
            m
            for m in events
            if m.start.timestamp() < start + 900
            and m.end.timestamp() > max(start, stamp)
        ]
        hidden.update(m.key for m in active[4:])
        if active:
            visible = active[:4]
            bands, extra = divmod(4, len(visible))
            lane = 0
            for index, meeting in enumerate(visible):
                height = bands + (index < extra)
                for _ in range(height):
                    cells[lane][column] = meeting
                    lane += 1
    segments = []
    for lane, row in enumerate(cells):
        start = 0
        while start < 48:
            meeting = row[start]
            end = start + 1
            while end < 48 and row[end] == meeting:
                end += 1
            if meeting:
                prior = next(
                    (
                        i
                        for i, s in enumerate(segments)
                        if s.start == start
                        and s.length == end - start
                        and s.lane + s.height == lane
                        and s.meeting == meeting.key
                    ),
                    None,
                )
                if prior is not None:
                    segments[prior] = replace(
                        segments[prior], height=segments[prior].height + 1
                    )
                else:
                    segments.append(
                        Segment(start, end - start, lane, 1, meeting.color, meeting.key)
                    )
            start = end
    return segments, len(hidden)


def clock_text(text):
    text = " ".join(text.split())
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore")[:64]


def scene_packet(
    segments,
    *,
    text="",
    duration=12,
    effect="none",
    colors=(15, 12),
    sound=0,
    meeting=None,
):
    """Build one acknowledged-write scene, retaining calendar under the text.

    Pulse is a firmware pixel effect, not calibrated brightness dimming.
    Glow/wave accept a pair of palette colors.
    """
    if effect not in EFFECTS or not 3 <= duration <= 30 or not 0 <= sound <= 17:
        raise ValueError("Invalid announcement settings")
    scene = CustomScene()

    def obj(method, start=0, life=1):
        return scene.object.add(method=method, startTime=start, lifeTime=life, result=0)

    base = [CLEAR] + [s.packed for s in segments]
    obj(2).fill.segment.extend(base)
    if text:
        obj(4, life=duration * 50).text.add(text=clock_text(text))
    restore_at = 0
    if effect in ("glow", "wave"):
        areas = [
            Segment(0, 48, 0, 1, colors[0]).packed,
            Segment(0, 48, 3, 1, colors[1]).packed,
        ]
        obj(2).fill.segment.extend([CLEAR] + areas)
        animation = obj(7, life=150).areaAnimation
        animation.type = 1 if effect == "wave" else 0
        animation.area.extend(areas)
        if effect == "wave":
            animation.wave.speed = 1
        else:
            animation.pulse.riseTime = animation.pulse.fallTime = 75
        restore_at = 150
    elif effect.startswith(("breath", "dim_")):
        pixels = [
            Segment(column, 1, lane, 1, s.color).packed
            for s in segments
            if s.meeting == meeting
            for lane in range(s.lane, s.lane + s.height)
            for column in range(s.start, s.start + s.length)
            if (column + lane) % 4 == 0
        ]
        half, cycles = {
            "breathing": (100, 0),
            "breath_1": (40, 1),
            "breath_2": (40, 2),
            "dim_once": (8, 1),
            "dim_twice": (8, 2),
        }[effect]
        if effect == "breathing":
            # Pulse the entire visible wedge, including thin overlap bands.
            pixels = [s.packed for s in segments if s.meeting == meeting]
        if pixels:
            restore_at = duration * 50 if effect == "breathing" else half * 2 * cycles
            animation = obj(7, life=restore_at).areaAnimation
            animation.type = 0
            animation.area.extend(pixels)
            animation.pulse.riseTime = animation.pulse.fallTime = half
    if restore_at:
        obj(2, start=restore_at).fill.segment.extend(base)
    if sound:
        obj(3).sound = sound
    packet = bytes([0, 0, 24 if text else 8, 7]) + scene.SerializeToString()
    if len(packet) > 512:
        raise ValueError(
            "Scene exceeds the BLE 512-byte write limit; select fewer calendars or a simpler effect"
        )
    return packet


def parse_events(response, calendar_colors, timezone):
    """HA calendar.get_events response; omit all-day and cancelled events."""
    meetings = []
    for entity, color in calendar_colors.items():
        for event in response[entity]["events"]:
            if event.get("status") == "cancelled":
                continue
            start, end = event.get("start", ""), event.get("end", "")
            if "T" not in start or "T" not in end:
                continue
            start = datetime.fromisoformat(start)
            end = datetime.fromisoformat(end)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone)
            title = event.get("summary", "Meeting")
            key = f"{entity}:{event.get('uid', title)}:{start.isoformat()}:{end.isoformat()}"
            meetings.append(Meeting(key, title, start, end, color))
    return list({m.key: m for m in meetings}.values())
