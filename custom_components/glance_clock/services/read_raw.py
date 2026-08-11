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


def _describe_gatt(connection_manager) -> dict:
    """Enumerate every service and characteristic, with what each one supports.

    The properties are the point. Whether the clock can push anything at all --
    a button press, a timer expiring -- comes down to whether some
    characteristic carries notify or indicate, and nothing we have documents
    that. Reading it off the device settles it without writing a listener first.
    """
    client = connection_manager.client
    if not client:
        raise ServiceValidationError("read_characteristic: no BLE client")

    services = []
    for service in client.services:
        chars = []
        for char in service.characteristics:
            chars.append(
                {
                    "uuid": str(char.uuid),
                    "handle": char.handle,
                    "properties": sorted(char.properties),
                    "descriptors": [str(d.uuid) for d in char.descriptors],
                }
            )
        services.append(
            {
                "uuid": str(service.uuid),
                "description": service.description,
                "characteristics": chars,
            }
        )

    notifiable = [
        c["uuid"]
        for s in services
        for c in s["characteristics"]
        if "notify" in c["properties"] or "indicate" in c["properties"]
    ]
    return {"services": services, "notifiable": notifiable}


async def handle_read_characteristic(
    hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall
) -> dict:
    """Read one characteristic and return its bytes as hex."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    connection_manager = entry_data.get("connection_manager")

    if not connection_manager or not connection_manager.is_connected:
        raise ServiceValidationError("read_characteristic: device not connected")

    name = str(call.data.get("characteristic", "settings")).strip().lower()

    if name == "list":
        return _describe_gatt(connection_manager)

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
