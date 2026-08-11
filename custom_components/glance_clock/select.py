"""Select platform for Glance Clock."""
import logging
import asyncio

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.restore_state import RestoreEntity

from .animation_state import get_animation_state
from .const import COLORS, DOMAIN, SOUNDS
from .entity import GlanceClockEntity
from .utils.led_utils import ANIMATIONS

_LOGGER = logging.getLogger(__name__)

# Date format options matching the web app
DATE_FORMAT_OPTIONS = {
    "Disabled": 0,
    "24 Jan": 1,
    "24 Tue": 2, 
    "Jan 24": 3,
    "Tue 24": 4,
}

DATE_FORMAT_REVERSE = {v: k for k, v in DATE_FORMAT_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glance Clock select entities."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = entry_data["mac_address"]
    name = entry_data["name"]
    connection_manager = entry_data["connection_manager"]

    entities = [
        GlanceClockDateFormatSelect(config_entry, mac_address, name, connection_manager),
        GlanceClockAnimationSelect(config_entry, mac_address, name, connection_manager),
        GlanceClockAnimationColorSelect(config_entry, mac_address, name, connection_manager),
        GlanceClockSoundSelect(config_entry, mac_address, name, connection_manager),
    ]

    async_add_entities(entities)


class GlanceClockDateFormatSelect(GlanceClockEntity, SelectEntity):
    """Date format selection for Glance Clock."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the date format select."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Date Format"
        self._attr_unique_id = f"{mac_address}_date_format"
        self._attr_icon = "mdi:calendar-text"
        self._attr_options = list(DATE_FORMAT_OPTIONS.keys())
        self._attr_current_option = None
        self._available = False

    @property
    def current_option(self) -> str | None:
        """Return the current selected option."""
        return self._attr_current_option

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self._connection_manager.is_connected

    async def async_select_option(self, option: str) -> None:
        """Select a new date format option."""
        if option not in DATE_FORMAT_OPTIONS:
            _LOGGER.error(f"Invalid date format option: {option}")
            return

        format_value = DATE_FORMAT_OPTIONS[option]
        success = await self._set_date_format(format_value)
        if success:
            self._attr_current_option = option
            self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Register callback with connection manager to immediately read state when connected
        if self._connection_manager:
            self._connection_manager.add_connection_callback(self._on_connection_established)
        
        # Try to read initial state from device immediately if already connected
        await self._update_initial_state()

    async def _on_connection_established(self) -> None:
        """Called when connection manager establishes a connection."""
        _LOGGER.info(f"🔗 Connection established for {self.name} - reading state immediately")
        
        # Read device state immediately upon connection
        await self.async_update()
        self.async_write_ha_state()

    async def _update_initial_state(self) -> None:
        """Update initial state in background to avoid blocking startup."""
        try:
            # Only add a small delay if not yet connected
            if not self._connection_manager.is_connected:
                await asyncio.sleep(2)  # Small delay to let connection stabilize
            await self.async_update()
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.debug(f"Could not read initial state for {self.name}: {e}")

    async def async_update(self) -> None:
        """Update the select state."""
        try:
            settings = await self._read_settings()
            if settings and "dateFormat" in settings:
                format_value = settings["dateFormat"]
                self._attr_current_option = DATE_FORMAT_REVERSE.get(format_value, "Disabled")
                self._available = True
                _LOGGER.debug(f"Date format updated: {format_value} -> {self._attr_current_option}")
            else:
                # Don't mark as unavailable if we just can't read settings
                # Only mark unavailable if device is actually disconnected
                self._available = self._connection_manager.is_connected
        except Exception as e:
            _LOGGER.debug(f"Error updating date format select: {e}")
            self._available = self._connection_manager.is_connected

    async def _set_date_format(self, format_value: int) -> bool:
        """Set date format setting on device."""
        try:
            if not self._connection_manager.is_connected:
                _LOGGER.warning("Device not connected, cannot set date format")
                return False

            # Create settings command
            settings_data = {
                "dateFormat": format_value
            }

            success = await self._write_settings(settings_data)
            if success:
                format_name = DATE_FORMAT_REVERSE.get(format_value, "Unknown")
                _LOGGER.info(f"Date format set to {format_name} ({format_value})")
                return True
            else:
                _LOGGER.error("Failed to set date format")
                return False

        except Exception as e:
            _LOGGER.error(f"Error setting date format: {e}")
            return False

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        # Remove connection callback
        if self._connection_manager:
            self._connection_manager.remove_connection_callback(self._on_connection_established)
        await super().async_will_remove_from_hass()

class GlanceClockAnimationChoice(GlanceClockEntity, SelectEntity, RestoreEntity):
    """One field of the animation the Run Animation button will send.

    This is a local choice, not device state -- the clock stores no pending
    animation -- so it restores from Home Assistant rather than from a read.
    """

    _state_key: str

    @property
    def current_option(self) -> str | None:
        """Return the chosen value."""
        return get_animation_state(self.hass, self._config_entry.entry_id)[self._state_key]

    @property
    def available(self) -> bool:
        """Always available; nothing is read from the clock."""
        return True

    async def async_select_option(self, option: str) -> None:
        """Remember the choice for the next run."""
        get_animation_state(self.hass, self._config_entry.entry_id)[self._state_key] = option
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the previous choice."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state in self.options:
            get_animation_state(self.hass, self._config_entry.entry_id)[self._state_key] = last.state
            self.async_write_ha_state()


class GlanceClockAnimationSelect(GlanceClockAnimationChoice):
    """Which animation to run."""

    _state_key = "animation"
    _attr_options = sorted(ANIMATIONS)

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the animation select."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Animation"
        self._attr_unique_id = f"{mac_address}_animation"
        self._attr_icon = "mdi:animation-play"


class GlanceClockAnimationColorSelect(GlanceClockAnimationChoice):
    """Which colour to tint the animation with."""

    _state_key = "color"
    # Black is deliberately excluded: it is a valid colour that renders
    # nothing, which is indistinguishable from a failure.
    _attr_options = sorted(name for name in COLORS if name != "black")

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the animation colour select."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Animation Colour"
        self._attr_unique_id = f"{mac_address}_animation_color"
        self._attr_icon = "mdi:palette"


class GlanceClockSoundSelect(GlanceClockAnimationChoice):
    """Which sound the Play Sound button plays.

    The clock has eighteen of them and their names say little about how they
    sound, so being able to step through them from the UI beats guessing.
    """

    _state_key = "sound"
    _attr_options = sorted(SOUNDS)

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the sound select."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Sound"
        self._attr_unique_id = f"{mac_address}_sound"
        self._attr_icon = "mdi:music-note"
