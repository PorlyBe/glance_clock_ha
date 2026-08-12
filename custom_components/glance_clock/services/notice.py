"""Notice service for Glance Clock."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from ..const import ANIMATIONS, DOMAIN, PRIORITIES, SOUNDS, TEXT_MODIFIERS
from ..utils.enums import lookup_enum
from ..utils.led_utils import resolve_color

_LOGGER = logging.getLogger(__name__)


def resolve_notice(data) -> dict:
    """Turn a notice's friendly names into the bytes the firmware expects.

    Every value here used to be looked up with a default, so a colour the
    palette does not have came out white, an unknown animation came out as a
    pulse, and a misspelled sound came out as silence. All three are
    indistinguishable from the clock ignoring the command, which is a bad way
    to spend an evening. They raise now, the way the LED services already do.
    """
    return {
        "animation": lookup_enum(ANIMATIONS, data.get("animation", "pulse"), "animation"),
        "sound": lookup_enum(SOUNDS, data.get("sound", "none"), "sound"),
        # Shared with the LED services rather than a plain table lookup, so the
        # aliases work here too. Somebody who learned that `green` draws a ring
        # will write it in a notice, and having it fail there only would be a
        # difference with no reason behind it.
        "color": resolve_color(data.get("color", "white")),
        "priority": lookup_enum(PRIORITIES, data.get("priority", "medium"), "priority"),
        "text_modifier": lookup_enum(
            TEXT_MODIFIERS, data.get("text_modifier", "none"), "text effect"
        ),
    }


async def handle_send_notice(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Handle sending notification notices to the device."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
    connection_manager = entry_data.get("connection_manager")

    if not notify_service:
        _LOGGER.error("Notification service not found for sending notice")
        return

    if connection_manager and not hasattr(notify_service, '_connection_manager'):
        notify_service._connection_manager = connection_manager

    text = call.data.get("text", "")

    try:
        notice = resolve_notice(call.data)
    except (ValueError, TypeError) as err:
        # Raised rather than logged: a name outside the firmware's own lists is
        # a mistake in the call, and defaulting it makes the service look like
        # it worked while showing something nobody asked for.
        raise ServiceValidationError(f"send_notice: {err}") from err

    success = await notify_service.async_send_notice(text=text, **notice)

    if success:
        _LOGGER.info(f"Notice sent successfully: {text}")
    else:
        _LOGGER.error(f"Failed to send notice: {text}")
