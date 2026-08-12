"""Light platform for Glance Clock."""
import logging
import asyncio
from typing import Any

from homeassistant.components.light import (
    LightEntity,
    ATTR_BRIGHTNESS,
)
from homeassistant.components.light.const import ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import GlanceClockEntity

_LOGGER = logging.getLogger(__name__)

# displayBrightness is not the 0-100 percentage the schema claims. Measured on
# hardware: the low byte is the manual level (1 barely visible, 255 full) and 0
# hands control back to the ambient light sensor. The upper bits made no
# distinguishable difference and are treated as opaque.
BRIGHTNESS_LEVEL_MASK = 0xFF


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glance Clock light entities."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = entry_data["mac_address"]
    name = entry_data["name"]
    connection_manager = entry_data["connection_manager"]

    entities = [
        GlanceClockDisplayLight(
            config_entry, mac_address, name, connection_manager),
    ]

    async_add_entities(entities)


class GlanceClockDisplayLight(GlanceClockEntity, LightEntity):
    """Display brightness light entity for Glance Clock."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the auto brightness light entity."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Auto Brightness"
        self._attr_unique_id = f"{mac_address}_auto_brightness"
        self._attr_icon = "mdi:brightness-auto"
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}
        self._brightness = None
        self._raw_brightness = None
        self._is_on = None
        self._available = False
        self._auto_brightness = False

    @property
    def brightness(self) -> int | None:
        """Return the brightness of the light (0-255). Only available in manual mode."""
        if self._is_on:  # Auto brightness mode - no manual brightness control
            return None
        return self._brightness

    @property
    def is_on(self) -> bool | None:
        """Return true if auto brightness is enabled (brightness = 0)."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self._connection_manager.is_connected

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {}
        if self._brightness is not None:
            if self._is_on:  # Auto brightness enabled
                attrs["brightness_mode"] = "auto"
                attrs["manual_brightness"] = "disabled"
                attrs["note"] = "Device automatically manages brightness"
            else:  # Manual brightness
                attrs["brightness_mode"] = "manual"
                # Calculate percentage for display
                percentage = round((self._brightness / 255) * 100)
                attrs["brightness_percentage"] = f"{percentage}%"
                attrs["manual_brightness"] = f"{self._brightness}/255"
        return attrs

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on auto brightness (set brightness to 0)."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        
        if brightness is not None:
            # If brightness is specified, turn OFF auto brightness and set manual brightness
            success = await self._set_brightness(brightness)
            if success:
                self._brightness = brightness
                self._is_on = False  # Auto brightness is "off" (manual mode)
                self._auto_brightness = False
                self._last_manual_brightness = brightness
                self.async_write_ha_state()
        else:
            # No brightness specified - turn ON auto brightness
            success = await self._set_brightness(0)
            if success:
                self._brightness = 0
                self._is_on = True  # Auto brightness is "on"
                self._auto_brightness = True
                self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off auto brightness (enable manual brightness control)."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        
        if brightness is not None:
            # Set specific manual brightness
            manual_brightness = brightness
        else:
            # Use previous manual brightness or default to 50%
            manual_brightness = getattr(self, '_last_manual_brightness', 128)
        
        success = await self._set_brightness(manual_brightness)
        if success:
            self._brightness = manual_brightness
            self._is_on = False  # Auto brightness is "off" (manual mode)
            self._auto_brightness = False
            self._last_manual_brightness = manual_brightness
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

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        # Remove connection callback
        if self._connection_manager:
            self._connection_manager.remove_connection_callback(self._on_connection_established)
        await super().async_will_remove_from_hass()

    async def async_update(self) -> None:
        """Update the light state."""
        try:
            settings = await self._read_settings()
            if settings and "displayBrightness" in settings:
                # Only the low byte is the manual level. Devices carry more in
                # the upper bits -- a working clock reported 2016768 (0x1EC600)
                # -- so treating the whole field as 0-255 both misreads the
                # state and destroys those bits when writing it back.
                self._raw_brightness = settings["displayBrightness"]
                brightness_value = self._raw_brightness & BRIGHTNESS_LEVEL_MASK
                self._brightness = brightness_value

                # Auto brightness is when the manual level is 0
                self._auto_brightness = (brightness_value == 0)
                
                # "Auto Brightness" is "on" when brightness = 0 (auto mode)
                self._is_on = self._auto_brightness
                
                # Store last manual brightness for when turning off auto mode
                if not self._auto_brightness:
                    self._last_manual_brightness = brightness_value
                
                self._available = True
                _LOGGER.debug(f"Auto brightness state updated: brightness={brightness_value}, auto={self._auto_brightness}, on={self._is_on}")
            else:
                # Don't mark as unavailable if we just can't read settings
                # Only mark unavailable if device is actually disconnected
                self._available = self._connection_manager.is_connected
        except Exception as e:
            _LOGGER.debug(f"Error updating auto brightness state: {e}")
            self._available = self._connection_manager.is_connected

    async def _set_brightness(self, brightness: int) -> bool:
        """Set brightness setting on device."""
        try:
            if not self._connection_manager.is_connected:
                _LOGGER.warning("Device not connected, cannot set brightness")
                return False

            # Keep whatever the device stores above the low byte. Those bits are
            # undocumented, they differ per device, and overwriting them with a
            # bare 0-255 value has been observed to leave the display in a state
            # where the rim points stop showing.
            raw = getattr(self, "_raw_brightness", None) or 0
            settings_data = {
                "displayBrightness": (raw & ~BRIGHTNESS_LEVEL_MASK)
                | (brightness & BRIGHTNESS_LEVEL_MASK)
            }

            success = await self._write_settings(settings_data)
            if success:
                if brightness == 0:
                    _LOGGER.info("Auto brightness enabled")
                else:
                    percentage = round((brightness / 255) * 100)
                    _LOGGER.info(f"Brightness set to {brightness} ({percentage}%)")
                return True
            else:
                _LOGGER.error("Failed to set brightness")
                return False

        except Exception as e:
            _LOGGER.error(f"Error setting brightness: {e}")
            return False