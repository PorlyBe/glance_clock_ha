"""Binary sensor platform for Glance Clock.

The clock reports what its display is doing on the scene_data characteristic,
one byte, pushed whenever it changes. Decoded on hardware:

    0x81   idle, digital time shown
    0x80   idle, digital time hidden
    0x00   busy -- a notice or scene is playing

So bit 7 means idle and bit 0 means the digital time is on screen. That makes
"is the clock busy" something to wait on rather than guess at: a notice sent
while another is playing is not queued, and the fifteen second scene cycle is
otherwise invisible from the outside.
"""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SCENE_DATA_CHARACTERISTIC_UUID

_LOGGER = logging.getLogger(__name__)

#: Bit 7: the display is idle. Clear means something is playing.
IDLE_BIT = 0x80

#: Bit 0: the digital time is on screen.
DIGITAL_CLOCK_BIT = 0x01


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glance Clock binary sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            GlanceClockBusyBinarySensor(
                data["mac_address"], data["name"], data.get("connection_manager")
            )
        ]
    )


class GlanceClockBusyBinarySensor(BinarySensorEntity):
    """True while the clock is showing a notice or a scene."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:play-box-outline"

    def __init__(self, mac_address, device_name, connection_manager):
        """Initialize the busy binary sensor."""
        self._mac_address = mac_address
        self._connection_manager = connection_manager
        self._attr_name = f"{device_name} Busy"
        self._attr_unique_id = f"{mac_address}_busy"
        self._attr_should_poll = False
        self._raw = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac_address)},
            connections={("bluetooth", self._mac_address)},
        )

    @property
    def available(self) -> bool:
        """Unavailable until the clock has said what it is doing."""
        return self._raw is not None

    @property
    def is_on(self) -> bool | None:
        """True while something is playing on the display."""
        if self._raw is None:
            return None
        return not self._raw & IDLE_BIT

    @property
    def extra_state_attributes(self) -> dict:
        """Carry the rest of the byte, and the byte itself."""
        if self._raw is None:
            return {}
        return {
            "digital_clock": bool(self._raw & DIGITAL_CLOCK_BIT),
            "raw": f"{self._raw:02x}",
        }

    async def async_added_to_hass(self) -> None:
        """Read the current state, then follow the clock's own updates."""
        await super().async_added_to_hass()

        @callback
        def _handle(event):
            if event.data.get("address") != self._mac_address:
                return
            if event.data.get("characteristic") != "scene_data":
                return
            payload = event.data.get("bytes") or []
            if not payload:
                return
            self._raw = payload[0]
            self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen("glance_clock_notification", _handle)
        )

        # The clock pushes on change, so without an initial read this stays
        # unknown until the next thing happens to play.
        await self._read_now()

    async def _read_now(self) -> None:
        """Read the characteristic directly, ignoring a clock that is not there."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            return
        try:
            data = await self._connection_manager.read_characteristic(
                SCENE_DATA_CHARACTERISTIC_UUID
            )
        except Exception as err:  # noqa: BLE001 -- bleak raises broadly
            _LOGGER.debug("Could not read display state: %s", err)
            return
        if data:
            self._raw = bytes(data)[0]
            self.async_write_ha_state()
