"""Notice service for Glance Clock."""
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry

from ..const import DOMAIN, ANIMATIONS, SOUNDS, COLORS, PRIORITIES, TEXT_MODIFIERS

_LOGGER = logging.getLogger(__name__)


async def handle_send_notice(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Handle sending notification notices to the device."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
    connection_manager = entry_data.get("connection_manager")

    if notify_service:
        if connection_manager and not hasattr(notify_service, '_connection_manager'):
            notify_service._connection_manager = connection_manager

        # Extract parameters
        text = call.data.get("text", "")
        animation_name = call.data.get("animation", "pulse")
        sound_name = call.data.get("sound", "none")
        color_name = call.data.get("color", "white")
        priority_name = call.data.get("priority", "medium")
        modifier_name = call.data.get("text_modifier", "none")

        # Convert names to numeric values
        animation = ANIMATIONS.get(animation_name, 1)  # Default to pulse
        sound = SOUNDS.get(sound_name, 0)  # Default to none
        color = COLORS.get(color_name, 12)  # Default to white
        priority = PRIORITIES.get(priority_name, 16)  # Default to medium
        text_modifier = TEXT_MODIFIERS.get(modifier_name, 0)  # Default to none

        success = await notify_service.async_send_notice(
            text=text,
            animation=animation,
            sound=sound,
            color=color,
            priority=priority,
            text_modifier=text_modifier
        )

        if success:
            _LOGGER.info(f"Notice sent successfully: {text}")
        else:
            _LOGGER.error(f"Failed to send notice: {text}")
    else:
        _LOGGER.error("Notification service not found for sending notice")
