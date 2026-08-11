"""Button platform for Glance Clock."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import GlanceClockEntity

_LOGGER = logging.getLogger(__name__)

# Hand calibration. The clock tracks its hands by counting motor steps from a
# reference position; it has no idea where they physically are. HOMING_START
# drives them to what it believes is 12:00 and holds them there, and
# HOMING_CONFIRM accepts wherever they are as the new reference.
HOMING_START = 43
HOMING_CONFIRM = 44


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glance Clock button entities."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = entry_data["mac_address"]
    name = entry_data["name"]
    connection_manager = entry_data["connection_manager"]

    async_add_entities(
        [
            GlanceClockCalibrateHandsButton(
                config_entry, mac_address, name, connection_manager),
            GlanceClockConfirmHandsButton(
                config_entry, mac_address, name, connection_manager),
        ]
    )


class GlanceClockCommandButton(GlanceClockEntity, ButtonEntity):
    """A button that sends one payload-less command to the clock."""

    _command: int

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._connection_manager.is_connected

    async def async_press(self) -> None:
        """Send the command."""
        if not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send %s", self.name)
            return

        # Padded to four bytes. Trailing zeroes may be omitted per the protocol
        # notes, but this is the form verified against hardware.
        command = bytes([self._command, 0, 0, 0])
        if await self._connection_manager.send_command(command):
            _LOGGER.info("%s sent", self.name)
        else:
            _LOGGER.error("Failed to send %s", self.name)


class GlanceClockCalibrateHandsButton(GlanceClockCommandButton):
    """Step one of hand calibration: drive the hands to the 12:00 reference."""

    _command = HOMING_START

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the calibrate hands button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Calibrate Hands"
        self._attr_unique_id = f"{mac_address}_calibrate_hands"
        self._attr_icon = "mdi:clock-edit-outline"


class GlanceClockConfirmHandsButton(GlanceClockCommandButton):
    """Step two of hand calibration: accept the current position as 12:00.

    Press this only once the hands physically point straight up. If one of them
    is off, pull it off its spindle and reseat it first -- never twist a hand
    while it is seated, that drives the gear train and can move the reference
    the clock just found.
    """

    _command = HOMING_CONFIRM

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the confirm hand position button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Confirm Hand Position"
        self._attr_unique_id = f"{mac_address}_confirm_hand_position"
        self._attr_icon = "mdi:check-decagram-outline"
