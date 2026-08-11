"""Button platform for Glance Clock."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .animation_state import get_animation_state
from .const import DOMAIN
from .entity import GlanceClockEntity
from .utils.led_utils import (
    PIXELS_PER_RING,
    RING_COUNT,
    check_speed,
    pack_segment,
    resolve_animation,
)

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
            GlanceClockRunAnimationButton(
                config_entry, mac_address, name, connection_manager),
            GlanceClockStopAnimationButton(
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
        # Names the precondition rather than the action: pressing this while the
        # hands are anywhere but straight up teaches the clock a wrong reference.
        self._attr_name = f"{device_name} Confirm Hand Positions at 12"
        self._attr_unique_id = f"{mac_address}_confirm_hand_position"
        self._attr_icon = "mdi:check-decagram-outline"


#: The animation buttons drive this slot, so running one replaces the last
#: rather than filling the clock's slots and making it cycle between them.
ANIMATION_SLOT = 0

#: Watchface: the animation and the digital time show at once. Verified on
#: hardware -- mode 24 alternates between them instead.
ANIMATION_MODE = 8


class GlanceClockRunAnimationButton(GlanceClockEntity, ButtonEntity):
    """Send the animation chosen by the animation selects and speed slider."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the run animation button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Run Animation"
        self._attr_unique_id = f"{mac_address}_run_animation"
        self._attr_icon = "mdi:play-circle-outline"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._connection_manager.is_connected

    async def async_press(self) -> None:
        """Pack the chosen settings and send them."""
        state = get_animation_state(self.hass, self._config_entry.entry_id)

        try:
            animation = resolve_animation(state["animation"])
            speed = check_speed(animation, state["speed"])
            segment = pack_segment(
                0,
                state["color"],
                length=PIXELS_PER_RING,
                ring=0,
                rings_tall=RING_COUNT,
            )
        except ValueError as err:
            # Most likely a negative speed on an animation that has no
            # direction. Say so; the slider cannot know which is selected.
            _LOGGER.error("Cannot run animation: %s", err)
            return

        notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(
            self._config_entry.entry_id
        )
        if not notify_service:
            _LOGGER.error("Notification service not available for animations")
            return

        if self._connection_manager and not hasattr(notify_service, "_connection_manager"):
            notify_service._connection_manager = self._connection_manager

        await notify_service.async_send_animation(
            animation,
            segment,
            speed=speed,
            mode=ANIMATION_MODE,
            slot=ANIMATION_SLOT,
        )


class GlanceClockStopAnimationButton(GlanceClockEntity, ButtonEntity):
    """Clear whatever the Run Animation button last sent."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the stop animation button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Stop Animation"
        self._attr_unique_id = f"{mac_address}_stop_animation"
        self._attr_icon = "mdi:stop-circle-outline"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._connection_manager.is_connected

    async def async_press(self) -> None:
        """Delete the animation slot."""
        notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(
            self._config_entry.entry_id
        )
        if not notify_service:
            _LOGGER.error("Notification service not available for animations")
            return

        if self._connection_manager and not hasattr(notify_service, "_connection_manager"):
            notify_service._connection_manager = self._connection_manager

        await notify_service.async_delete_scene(ANIMATION_SLOT)
