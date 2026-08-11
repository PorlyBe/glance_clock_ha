"""Read a GATT characteristic and hand the bytes back to the caller.

The clock exposes more characteristics than this integration reads, and what is
in them is not documented anywhere we have. Logging the bytes is not enough --
this deployment writes no log file to disk, and a message nobody can retrieve
is the same as no message. So this returns a service response instead, which
comes straight back to whoever made the call.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ..const import (
    DOMAIN,
    GLANCE_CHARACTERISTIC_UUID,
    SCENE_DATA_CHARACTERISTIC_UUID,
    SCENE_STATE_DATA_CHARACTERISTIC_UUID,
)

_LOGGER = logging.getLogger(__name__)

#: Short names for the characteristics we know about, so a call does not have to
#: carry a UUID around.
KNOWN_CHARACTERISTICS = {
    "settings": GLANCE_CHARACTERISTIC_UUID,
    "scene_data": SCENE_DATA_CHARACTERISTIC_UUID,
    "scene_state": SCENE_STATE_DATA_CHARACTERISTIC_UUID,
}


async def handle_read_characteristic(
    hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall
) -> dict:
    """Read one characteristic and return its bytes as hex."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    connection_manager = entry_data.get("connection_manager")

    if not connection_manager or not connection_manager.is_connected:
        raise ServiceValidationError("read_characteristic: device not connected")

    name = str(call.data.get("characteristic", "settings")).strip().lower()
    uuid = KNOWN_CHARACTERISTICS.get(name)
    if uuid is None:
        if "-" in name:
            uuid = name
        else:
            raise ServiceValidationError(
                f"read_characteristic: unknown characteristic '{name}'; expected one of "
                f"{', '.join(sorted(KNOWN_CHARACTERISTICS))}, or a full UUID"
            )

    try:
        data = await connection_manager.read_characteristic(uuid)
    except Exception as err:  # noqa: BLE001 -- bleak raises a wide range here
        raise ServiceValidationError(f"read_characteristic: {err}") from err

    data = bytes(data)
    return {
        "characteristic": name,
        "uuid": uuid,
        "length": len(data),
        "hex": data.hex(),
        "bytes": list(data),
    }
