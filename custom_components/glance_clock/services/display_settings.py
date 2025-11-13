"""Display settings services for Glance Clock."""
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def handle_update_display_settings(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Handle display settings update requests."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
    connection_manager = entry_data.get("connection_manager")

    if notify_service:
        if connection_manager and not hasattr(notify_service, '_connection_manager'):
            notify_service._connection_manager = connection_manager

        success = await notify_service.async_write_settings(call.data)
        if success:
            _LOGGER.info("Display settings updated successfully")
        else:
            _LOGGER.error("Failed to update display settings")
    else:
        _LOGGER.error("Notification service not found for display settings")


async def handle_read_current_settings(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Handle reading current device settings."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
    connection_manager = entry_data.get("connection_manager")

    if notify_service:
        if connection_manager and not hasattr(notify_service, '_connection_manager'):
            notify_service._connection_manager = connection_manager

        settings = await notify_service.async_read_current_settings_safe()
        if settings:
            _LOGGER.debug("Current settings read successfully:")
            for key, value in settings.items():
                _LOGGER.debug(f"  {key}: {value}")
        else:
            _LOGGER.error("Failed to read current settings")
    else:
        _LOGGER.error("Notification service not found for reading settings")
