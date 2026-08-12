"""Scheduled Do-Not-Disturb service for Glance Clock."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def handle_set_dnd_schedule(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Set the recurring Do-Not-Disturb window on the device.

    The window is stored on the clock itself in a nested submessage, separate
    from the permanentDND flag, and survives Home Assistant restarts.
    """
    entry_data = hass.data[DOMAIN][entry.entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
    connection_manager = entry_data.get("connection_manager")

    if not notify_service:
        _LOGGER.error("Notification service not found for DND schedule")
        return

    if connection_manager and not hasattr(notify_service, "_connection_manager"):
        notify_service._connection_manager = connection_manager

    settings = {}
    if "from_hour" in call.data:
        settings["dndFromHour"] = int(call.data["from_hour"])
    if "till_hour" in call.data:
        settings["dndTillHour"] = int(call.data["till_hour"])
    if "recurring" in call.data:
        settings["dndRecurring"] = bool(call.data["recurring"])

    if not settings:
        _LOGGER.error("set_dnd_schedule called with nothing to change")
        return

    for key in ("dndFromHour", "dndTillHour"):
        if key in settings and not 0 <= settings[key] <= 23:
            _LOGGER.error("%s must be an hour between 0 and 23", key)
            return

    if await notify_service.async_write_settings(settings):
        _LOGGER.info("DND schedule updated: %s", settings)
    else:
        _LOGGER.error("Failed to update DND schedule")


async def handle_read_dnd_schedule(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Log the device's current Do-Not-Disturb window."""
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
    if not notify_service:
        _LOGGER.error("Notification service not found for DND schedule")
        return

    settings = await notify_service.async_read_current_settings_safe()
    if not settings:
        _LOGGER.error("Could not read settings from device")
        return

    if settings.get("dndFromHour") is None:
        _LOGGER.info("No DND schedule is stored on this device")
        return

    _LOGGER.info(
        "DND schedule: %02d:00 -> %02d:00 (recurring: %s)",
        settings["dndFromHour"],
        settings["dndTillHour"],
        settings["dndRecurring"],
    )
