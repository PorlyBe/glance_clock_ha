"""Timer service for Glance Clock."""
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def handle_send_timer(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Handle sending a timer scene to the device."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
    connection_manager = entry_data.get("connection_manager")

    if notify_service:
        if connection_manager and not hasattr(notify_service, '_connection_manager'):
            notify_service._connection_manager = connection_manager

        countdown = call.data.get("countdown")
        intervals = call.data.get("intervals", [])
        final_text = call.data.get("final_text", "")

        success = await notify_service.async_send_timer(
            countdown=countdown,
            intervals=intervals,
            final_text=final_text
        )

        if success:
            _LOGGER.info(f"Timer sent successfully: {countdown}s")
        else:
            _LOGGER.error(f"Failed to send timer: {countdown}s")
    else:
        _LOGGER.error("Notification service not found for sending timer")
