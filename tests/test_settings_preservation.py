"""Settings writes must not destroy fields this integration does not model.

The device's Settings message carries more than the bundled schema describes.
A real clock (model 666, firmware 1.6.7) reports a nested Do-Not-Disturb
schedule in field 1 and an undocumented field 15, and does *not* report field
13. Rebuilding the message from the handful of named fields silently deletes
the first two and invents the third.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "glance_clock"))

from glance_pb2 import Settings  # type: ignore  # noqa: E402

#: Captured over BLE from a real clock before anything was written to it.
REAL_SETTINGS = bytes.fromhex(
    "0a060801101518071001180020012800480150808c7b580160007800"
)


def field_numbers(data: bytes) -> list[int]:
    """List the protobuf field numbers present in a serialised message."""
    found: list[int] = []
    pos = 0
    while pos < len(data):
        key = 0
        shift = 0
        while True:
            byte = data[pos]
            pos += 1
            key |= (byte & 0x7F) << shift
            if not byte & 0x80:
                break
            shift += 7
        field, wire_type = key >> 3, key & 0x07
        if wire_type == 0:
            while data[pos] & 0x80:
                pos += 1
            pos += 1
        elif wire_type == 2:
            length = data[pos]
            pos += 1 + length
        else:
            raise AssertionError(f"unexpected wire type {wire_type}")
        found.append(field)
    return sorted(found)


def test_the_real_message_carries_unmodelled_fields() -> None:
    assert field_numbers(REAL_SETTINGS) == [1, 2, 3, 4, 5, 9, 10, 11, 12, 15]


def test_parsing_and_reserialising_is_byte_identical() -> None:
    """The premise of the fix: protobuf round-trips what it does not model."""
    settings = Settings()
    settings.ParseFromString(REAL_SETTINGS)
    assert settings.SerializeToString() == REAL_SETTINGS


def test_patching_one_field_preserves_everything_else() -> None:
    settings = Settings()
    settings.ParseFromString(REAL_SETTINGS)
    settings.timeFormat12 = True

    written = settings.SerializeToString()
    assert field_numbers(written) == field_numbers(REAL_SETTINGS)
    assert settings.dnd.fromHour == 21
    assert settings.dnd.tillHour == 7


def test_rebuilding_from_named_fields_loses_data() -> None:
    """Guards the regression: this is what the old code did."""
    rebuilt = Settings()
    rebuilt.nightModeEnabled = True
    rebuilt.pointsAlwaysEnabled = True
    rebuilt.displayBrightness = 2016768
    rebuilt.timeModeEnable = True
    rebuilt.timeFormat12 = True
    rebuilt.permanentDND = False
    rebuilt.permanentMute = True
    rebuilt.dateFormat = 0
    rebuilt.mgrUserActivityTimeout = 600

    present = field_numbers(rebuilt.SerializeToString())
    assert 1 not in present, "DND schedule survived a rebuild -- test is wrong"
    assert 15 not in present, "undocumented field survived -- test is wrong"
    assert 13 in present, "field 13 was not invented -- test is wrong"
