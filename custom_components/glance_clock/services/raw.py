"""Send a raw command frame to the clock.

The firmware understands a good deal more than this integration models, and
some of it only matters in situations that are awkward to reach -- scene
playback being left stopped after a power cycle, for one. This service is the
escape hatch for those, and for driving the clock from Node-RED without waiting
for a named service to exist.

A frame is a command byte, up to three modifier bytes, and an optional payload.
Trailing modifiers are padded with zeroes, matching every frame we have
observed working on hardware.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

#: Commands that would take the clock away from its owner. Clearing the bonds
#: unpairs it, and there is no pairing button to recover with -- the clock has
#: exactly one button. Clearing user info wipes what the dead cloud service can
#: no longer restore. Neither belongs behind a service call that exists for
#: experimentation.
BLOCKED_COMMANDS = {
    42: "BondsClear -- would unpair the clock, and it has no pairing button to recover with",
    50: "UserInfoClear -- would wipe user data that the manufacturer's servers can no longer restore",
}

MAX_MODIFIERS = 3


def _parse_payload(value) -> bytes:
    """Accept a hex string, a list of ints, or nothing."""
    if value is None or value == "":
        return b""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if isinstance(value, (list, tuple)):
        return bytes(int(b) & 0xFF for b in value)

    text = str(value).strip().replace(" ", "").replace(":", "")
    if text.lower().startswith("0x"):
        text = text[2:]
    if len(text) % 2:
        raise ValueError(f"payload hex must have an even number of digits, got {len(text)}")
    try:
        return bytes.fromhex(text)
    except ValueError as err:
        raise ValueError(f"payload is not valid hex: {err}") from err


def build_frame(command: int, modifiers, payload) -> bytes:
    """Build one command frame, or explain why it cannot be built."""
    command = int(command)
    if not 0 <= command <= 255:
        raise ValueError(f"command must be 0-255, got {command}")
    if command in BLOCKED_COMMANDS:
        raise ValueError(f"command {command} is blocked: {BLOCKED_COMMANDS[command]}")

    if modifiers is None:
        modifiers = []
    elif isinstance(modifiers, int):
        modifiers = [modifiers]
    modifiers = list(modifiers)

    if len(modifiers) > MAX_MODIFIERS:
        raise ValueError(f"a frame carries at most {MAX_MODIFIERS} modifiers, got {len(modifiers)}")
    for index, mod in enumerate(modifiers):
        if not 0 <= int(mod) <= 255:
            raise ValueError(f"modifier {index} must be 0-255, got {mod}")

    head = [command, *(int(m) & 0xFF for m in modifiers)]
    head += [0] * (1 + MAX_MODIFIERS - len(head))
    return bytes(head) + _parse_payload(payload)


async def handle_send_command(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Send one raw frame to the clock's control characteristic."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    connection_manager = entry_data.get("connection_manager")

    if not connection_manager or not connection_manager.is_connected:
        _LOGGER.error("send_command: device not connected")
        return

    try:
        frame = build_frame(
            call.data.get("command"),
            call.data.get("modifiers"),
            call.data.get("payload"),
        )
    except (ValueError, TypeError) as err:
        _LOGGER.error("send_command: %s", err)
        return

    _LOGGER.info("send_command: sending %s", frame.hex())
    if await connection_manager.send_command(frame):
        _LOGGER.info("send_command: sent successfully")
    else:
        _LOGGER.error("send_command: failed to send %s", frame.hex())
