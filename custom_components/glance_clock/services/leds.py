"""LED ring services for Glance Clock."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from ..const import DOMAIN
from ..utils.led_utils import resolve_mode, segments_from_config

_LOGGER = logging.getLogger(__name__)


def _notify_service(hass: HomeAssistant, entry: ConfigEntry):
    """Fetch the notification service, wiring up the connection manager."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
    connection_manager = entry_data.get("connection_manager")

    if notify_service and connection_manager and not hasattr(notify_service, "_connection_manager"):
        notify_service._connection_manager = connection_manager

    return notify_service


async def handle_set_leds(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Light areas of the clock's four LED rings."""
    notify_service = _notify_service(hass, entry)
    if not notify_service:
        _LOGGER.error("Notification service not found for set_leds")
        return

    try:
        segments = segments_from_config(call.data.get("segments") or [])
        mode = resolve_mode(call.data.get("mode", "watchface"))
    except (ValueError, TypeError) as err:
        # Bad geometry is a user mistake, not a bug -- say what was wrong
        # rather than letting a malformed frame reach the clock.
        _LOGGER.error("set_leds: %s", err)
        return

    await notify_service.async_send_custom_scene(
        segments,
        mode=mode,
        slot=int(call.data.get("slot", 0)),
        life_time=int(call.data.get("life_time", 50)),
    )


async def handle_clear_leds(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Remove a scene previously sent with set_leds."""
    notify_service = _notify_service(hass, entry)
    if not notify_service:
        _LOGGER.error("Notification service not found for clear_leds")
        return

    await notify_service.async_delete_scene(int(call.data.get("slot", 0)))
