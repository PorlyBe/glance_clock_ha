"""Base entity for Glance Clock devices."""
import logging
import asyncio
from datetime import datetime, timedelta
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class GlanceClockEntity(Entity):
    """Base class for Glance Clock entities."""

    def __init__(self, config_entry: ConfigEntry, mac_address: str, device_name: str, connection_manager):
        """Initialize the entity."""
        self._config_entry = config_entry
        self._mac_address = mac_address
        self._device_name = device_name
        self._connection_manager = connection_manager
        self._attr_should_poll = False  # Disable automatic polling to prevent timeout warnings
        self._last_settings_read = None
        self._cached_settings = None
        self._settings_cache_duration = timedelta(minutes=5)  # Cache settings for 5 minutes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac_address)},
            connections={("bluetooth", self._mac_address)},
            name=self._device_name,
            manufacturer="Glance",
            model="Clock",
        )

    async def _read_settings(self) -> dict | None:
        """Read current settings from device with caching."""
        try:
            # Check if we have recent cached settings
            now = datetime.now()
            if (self._cached_settings and self._last_settings_read and
                now - self._last_settings_read < self._settings_cache_duration):
                _LOGGER.debug("Using cached settings")
                return self._cached_settings

            if not self._connection_manager or not self._connection_manager.is_connected:
                _LOGGER.debug("Device not connected, entities will be unavailable")
                return None

            # Get the notification service to handle settings reading
            notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(self._config_entry.entry_id)
            if notify_service:
                _LOGGER.debug("Attempting to read settings from device")
                
                # Try to read settings using the safe method
                try:
                    settings = await notify_service.async_read_current_settings_safe()
                    if settings:
                        self._cached_settings = settings
                        self._last_settings_read = now
                        _LOGGER.debug("Settings cached successfully")
                        return settings
                    else:
                        _LOGGER.debug("Settings reading disabled - entities will be unavailable")
                        return None
                except Exception as read_error:
                    _LOGGER.debug(f"Settings read failed - entities will be unavailable: {read_error}")
                    return None
            else:
                _LOGGER.error("Notification service not available")
                return None

        except Exception as e:
            _LOGGER.error(f"Error reading settings: {e}")
            return None

    def _get_default_settings(self) -> dict:
        """Get default settings when device settings can't be read."""
        return {
            "nightModeEnabled": True,
            "pointsAlwaysEnabled": False,
            "displayBrightness": 128,
            "timeModeEnable": True,
            "timeFormat12": False,
            "permanentDND": False,
            "permanentMute": False,
            "dateFormat": 0,  # DateDisabled
            "mgrUserActivityTimeout": 600,
        }

    async def _get_settings_with_memory(self) -> dict:
        """Get settings with memory of user changes."""
        # If we have cached settings that include user changes, use them
        if self._cached_settings:
            return self._cached_settings
        
        # Otherwise, use defaults (since we can't read from device reliably)
        defaults = self._get_default_settings()
        self._cached_settings = defaults
        return defaults

    async def _write_settings(self, settings_data: dict) -> bool:
        """Write settings to device and update local cache."""
        try:
            if not self._connection_manager or not self._connection_manager.is_connected:
                _LOGGER.debug("Device not connected, cannot write settings")
                return False

            # Get the notification service to handle settings writing
            notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(self._config_entry.entry_id)
            if notify_service:
                # Ensure the notification service has the connection manager
                if self._connection_manager and not hasattr(notify_service, '_connection_manager'):
                    notify_service._connection_manager = self._connection_manager

                success = await notify_service.async_write_settings(settings_data)
                if success:
                    # Create initial settings cache with defaults if we don't have any
                    if not self._cached_settings:
                        self._cached_settings = self._get_default_settings()
                    
                    # Update local cache with the new settings
                    self._cached_settings.update(settings_data)
                    self._last_settings_read = datetime.now()
                    _LOGGER.debug(f"Settings cache updated with: {settings_data}")
                    _LOGGER.info("Settings written successfully - entities are now available")
                return success
            else:
                _LOGGER.error("Notification service not available for settings writing")
                return False

        except Exception as e:
            _LOGGER.error(f"Error writing settings: {e}")
            return False

    def invalidate_settings_cache(self) -> None:
        """Invalidate the settings cache to force a fresh read."""
        self._last_settings_read = None
        self._cached_settings = None
        _LOGGER.debug("Settings cache manually invalidated")