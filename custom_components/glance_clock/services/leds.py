"""LED ring services for Glance Clock."""
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from ..const import DOMAIN
from ..utils.led_utils import (
    ANIMATION_SWEEP,
    DISPLAY_MODES,
    GIF_LENGTH_MULTIPLE,
    PIXELS_PER_RING,
    check_speed,
    pack_segment,
    resolve_animation,
    resolve_mode,
    scene_steps_from_config,
    segments_from_config,
)

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


async def handle_set_scene(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Send a timed sequence of fills the clock plays itself."""
    notify_service = _notify_service(hass, entry)
    if not notify_service:
        _LOGGER.error("Notification service not found for set_scene")
        return

    try:
        steps = scene_steps_from_config(
            call.data.get("steps") or [],
            default_frames=int(call.data.get("default_frames", 25)),
        )
        mode = resolve_mode(call.data.get("mode", "watchface"))
    except (ValueError, TypeError) as err:
        _LOGGER.error("set_scene: %s", err)
        return

    if mode == DISPLAY_MODES["watchface"] and any(s["type"] == "text" for s in steps):
        # The digital clockface owns the matrix in this mode, so the text has
        # nowhere to go and simply never appears. Silence here looks like a
        # broken service.
        _LOGGER.warning(
            "set_scene: text steps do not render in 'watchface' mode, because the "
            "digital clockface occupies the matrix. Use mode 'exclusive' for text."
        )

    await notify_service.async_send_scene(
        steps,
        mode=mode,
        slot=int(call.data.get("slot", 0)),
    )


async def handle_set_animation(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Run a firmware animation on the LED rings."""
    notify_service = _notify_service(hass, entry)
    if not notify_service:
        _LOGGER.error("Notification service not found for set_animation")
        return

    try:
        animation = resolve_animation(call.data.get("animation", "fire"))
        speed = check_speed(animation, call.data.get("speed", 3))
        mode = resolve_mode(call.data.get("mode", "watchface"))
        length = int(call.data.get("length", PIXELS_PER_RING))

        if animation != ANIMATION_SWEEP and length % GIF_LENGTH_MULTIPLE:
            # The clock rounds these down itself, so say what will happen
            # rather than letting the result look like a bug.
            _LOGGER.warning(
                "'%s' only renders lengths that are a multiple of %d; the clock "
                "will round %d down",
                animation, GIF_LENGTH_MULTIPLE, length,
            )

        segment = pack_segment(
            int(call.data.get("start", 0)),
            call.data.get("color", "white"),
            length=length,
            ring=int(call.data.get("ring", 0)),
            rings_tall=int(call.data.get("rings_tall", 4)),
        )
    except (ValueError, TypeError) as err:
        _LOGGER.error("set_animation: %s", err)
        return

    await notify_service.async_send_animation(
        animation,
        segment,
        speed=speed,
        mode=mode,
        slot=int(call.data.get("slot", 0)),
        life_time=int(call.data.get("life_time", 2500)),
    )


async def handle_clear_leds(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Remove a scene previously sent with set_leds."""
    notify_service = _notify_service(hass, entry)
    if not notify_service:
        _LOGGER.error("Notification service not found for clear_leds")
        return

    await notify_service.async_delete_scene(int(call.data.get("slot", 0)))
