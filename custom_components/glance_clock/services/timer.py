"""Timer service for Glance Clock."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

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

        # `countdown` is the delay BEFORE the timer starts, not how long it
        # runs -- the stages live in `intervals`. Sending a countdown with no
        # intervals asks the clock to wait and then run nothing, and it does
        # exactly that: the call succeeds and the display never changes.
        # Verified on hardware 2026-08-12, filmed, thirty seconds of nothing.
        countdown = call.data.get("countdown") or 0
        intervals = call.data.get("intervals") or []
        final_text = call.data.get("final_text", "")

        if not intervals:
            raise ServiceValidationError(
                "send_timer: a timer needs at least one entry in 'intervals', "
                "each with a 'duration' in seconds. 'countdown' is the delay "
                "before the timer starts, not the time it counts, and "
                "'final_text' is only shown once the intervals have run -- so "
                "a call without intervals reaches the clock and displays "
                "nothing at all."
            )

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
