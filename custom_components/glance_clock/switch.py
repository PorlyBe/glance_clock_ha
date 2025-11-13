"""Switch platform for Glance Clock."""
import logging
import asyncio
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN
from .entity import GlanceClockEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glance Clock switch entities."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = entry_data["mac_address"]
    name = entry_data["name"]
    connection_manager = entry_data["connection_manager"]

    entities = [
        GlanceClockNightModeSwitch(config_entry, mac_address, name, connection_manager),
        GlanceClockTimePointsSwitch(config_entry, mac_address, name, connection_manager),
        GlanceClockTimeModeSwitch(config_entry, mac_address, name, connection_manager),
        GlanceClockTimeFormatSwitch(config_entry, mac_address, name, connection_manager),
    ]

    async_add_entities(entities)


class GlanceClockNightModeSwitch(GlanceClockEntity, SwitchEntity):
    """Night mode switch for Glance Clock."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the night mode switch."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Night Mode"
        self._attr_unique_id = f"{mac_address}_night_mode"
        self._attr_icon = "mdi:weather-night"
        self._is_on = None
        self._available = False

    @property
    def is_on(self) -> bool | None:
        """Return true if night mode is on."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self._connection_manager.is_connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on night mode."""
        success = await self._set_night_mode(True)
        if success:
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off night mode."""
        success = await self._set_night_mode(False)
        if success:
            self._is_on = False
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
        _LOGGER.debug(f"🔗 Connection established for {self.name} - reading state immediately")
        
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
        """Update the switch state."""
        try:
            settings = await self._read_settings()
            if settings and "nightModeEnabled" in settings:
                self._is_on = settings["nightModeEnabled"]
                self._available = True
            else:
                # Don't mark as unavailable if we just can't read settings
                # Only mark unavailable if device is actually disconnected
                self._available = self._connection_manager.is_connected
        except Exception as e:
            _LOGGER.debug(f"Error updating night mode switch: {e}")
            self._available = self._connection_manager.is_connected

    async def _set_night_mode(self, enabled: bool) -> bool:
        """Set night mode setting on device."""
        try:
            if not self._connection_manager.is_connected:
                _LOGGER.warning("Device not connected, cannot set night mode")
                return False

            # Create settings command
            settings_data = {
                "nightModeEnabled": enabled
            }

            success = await self._write_settings(settings_data)
            if success:
                _LOGGER.info(f"Night mode {'enabled' if enabled else 'disabled'}")
                return True
            else:
                _LOGGER.error("Failed to set night mode")
                return False

        except Exception as e:
            _LOGGER.error(f"Error setting night mode: {e}")
            return False

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        # Remove connection callback
        if self._connection_manager:
            self._connection_manager.remove_connection_callback(self._on_connection_established)
        await super().async_will_remove_from_hass()


class GlanceClockTimePointsSwitch(GlanceClockEntity, SwitchEntity):
    """Time points always visible switch for Glance Clock."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the time points switch."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Always Show Time Points"
        self._attr_unique_id = f"{mac_address}_time_points"
        self._attr_icon = "mdi:clock-time-two-outline"
        self._is_on = None
        self._available = False

    @property
    def is_on(self) -> bool | None:
        """Return true if time points are always shown."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self._connection_manager.is_connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on always show time points."""
        success = await self._set_time_points(True)
        if success:
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off always show time points."""
        success = await self._set_time_points(False)
        if success:
            self._is_on = False
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
        _LOGGER.debug(f"🔗 Connection established for {self.name} - reading state immediately")
        
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
        """Update the switch state."""
        try:
            settings = await self._read_settings()
            if settings and "pointsAlwaysEnabled" in settings:
                self._is_on = settings["pointsAlwaysEnabled"]
                self._available = True
            else:
                # Don't mark as unavailable if we just can't read settings
                # Only mark unavailable if device is actually disconnected
                self._available = self._connection_manager.is_connected
        except Exception as e:
            _LOGGER.debug(f"Error updating time points switch: {e}")
            self._available = self._connection_manager.is_connected

    async def _set_time_points(self, enabled: bool) -> bool:
        """Set time points setting on device."""
        try:
            if not self._connection_manager.is_connected:
                _LOGGER.warning("Device not connected, cannot set time points")
                return False

            # Create settings command
            settings_data = {
                "pointsAlwaysEnabled": enabled
            }

            success = await self._write_settings(settings_data)
            if success:
                _LOGGER.info(f"Always show time points {'enabled' if enabled else 'disabled'}")
                return True
            else:
                _LOGGER.error("Failed to set time points setting")
                return False

        except Exception as e:
            _LOGGER.error(f"Error setting time points: {e}")
            return False

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        # Remove connection callback
        if self._connection_manager:
            self._connection_manager.remove_connection_callback(self._on_connection_established)
        await super().async_will_remove_from_hass()


class GlanceClockTimeModeSwitch(GlanceClockEntity, SwitchEntity):
    """Time mode switch for Glance Clock."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the time mode switch."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Time Mode"
        self._attr_unique_id = f"{mac_address}_time_mode"
        self._attr_icon = "mdi:clock"
        self._is_on = None
        self._available = False

    @property
    def is_on(self) -> bool | None:
        """Return true if time mode is enabled."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self._connection_manager.is_connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on time mode."""
        success = await self._set_time_mode(True)
        if success:
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off time mode."""
        success = await self._set_time_mode(False)
        if success:
            self._is_on = False
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
        _LOGGER.debug(f"🔗 Connection established for {self.name} - reading state immediately")
        
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
        """Update the switch state."""
        try:
            settings = await self._read_settings()
            if settings and "timeModeEnable" in settings:
                self._is_on = settings["timeModeEnable"]
                self._available = True
            else:
                # Don't mark as unavailable if we just can't read settings
                # Only mark unavailable if device is actually disconnected
                self._available = self._connection_manager.is_connected
        except Exception as e:
            _LOGGER.debug(f"Error updating time mode switch: {e}")
            self._available = self._connection_manager.is_connected

    async def _set_time_mode(self, enabled: bool) -> bool:
        """Set time mode setting on device."""
        try:
            if not self._connection_manager.is_connected:
                _LOGGER.warning("Device not connected, cannot set time mode")
                return False

            # Create settings command
            settings_data = {
                "timeModeEnable": enabled
            }

            success = await self._write_settings(settings_data)
            if success:
                _LOGGER.info(f"Time mode {'enabled' if enabled else 'disabled'}")
                return True
            else:
                _LOGGER.error("Failed to set time mode")
                return False

        except Exception as e:
            _LOGGER.error(f"Error setting time mode: {e}")
            return False

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        # Remove connection callback
        if self._connection_manager:
            self._connection_manager.remove_connection_callback(self._on_connection_established)
        await super().async_will_remove_from_hass()


class GlanceClockTimeFormatSwitch(GlanceClockEntity, SwitchEntity):
    """12-hour format switch for Glance Clock."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the 12-hour format switch."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} 12-Hour Format"
        self._attr_unique_id = f"{mac_address}_12_hour_format"
        self._attr_icon = "mdi:clock-time-twelve-outline"
        self._is_on = None
        self._available = False

    @property
    def is_on(self) -> bool | None:
        """Return true if 12-hour format is enabled."""
        return self._is_on

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self._connection_manager.is_connected

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on 12-hour format."""
        success = await self._set_time_format(True)
        if success:
            self._is_on = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off 12-hour format (use 24-hour)."""
        success = await self._set_time_format(False)
        if success:
            self._is_on = False
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
        _LOGGER.debug(f"🔗 Connection established for {self.name} - reading state immediately")
        
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
        """Update the switch state."""
        try:
            settings = await self._read_settings()
            if settings and "timeFormat12" in settings:
                self._is_on = settings["timeFormat12"]
                self._available = True
            else:
                # Don't mark as unavailable if we just can't read settings
                # Only mark unavailable if device is actually disconnected
                self._available = self._connection_manager.is_connected
        except Exception as e:
            _LOGGER.debug(f"Error updating time format switch: {e}")
            self._available = self._connection_manager.is_connected

    async def _set_time_format(self, twelve_hour: bool) -> bool:
        """Set time format setting on device."""
        try:
            if not self._connection_manager.is_connected:
                _LOGGER.warning("Device not connected, cannot set time format")
                return False

            # Create settings command
            settings_data = {
                "timeFormat12": twelve_hour
            }

            success = await self._write_settings(settings_data)
            if success:
                format_name = "12-hour" if twelve_hour else "24-hour"
                _LOGGER.info(f"Time format set to {format_name}")
                return True
            else:
                _LOGGER.error("Failed to set time format")
                return False

        except Exception as e:
            _LOGGER.error(f"Error setting time format: {e}")
            return False

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        # Remove connection callback
        if self._connection_manager:
            self._connection_manager.remove_connection_callback(self._on_connection_established)
        await super().async_will_remove_from_hass()