"""HA-native app actions: calendar providers and authentication remain in HA."""

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util

from ..const import COLORS, DOMAIN, SOUNDS
from .scenes import parse_events

_LOGGER = logging.getLogger(__name__)

APP_SERVICES = (
    "show_calendar",
    "announce_calendar",
    "announce",
)
COLOR = vol.All(vol.Coerce(int), vol.Range(min=1, max=53))
COMMON = {vol.Optional("entry_id"): cv.string}
ANNOUNCEMENT = {
    **COMMON,
    vol.Optional("duration", default=12): vol.All(
        vol.Coerce(int), vol.Range(min=3, max=30)
    ),
    vol.Optional("sound", default="none"): vol.In(SOUNDS),
}
CALENDAR = vol.Schema(
    {
        **COMMON,
        vol.Required("calendars"): vol.All(
            {cv.entity_domain("calendar"): vol.Any(vol.In(COLORS), COLOR)},
            vol.Length(max=16),
        ),
    }
)
CALENDAR_NOTICE = vol.Schema(
    {
        **ANNOUNCEMENT,
        vol.Optional("effect", default="breathing"): vol.In(
            ("none", "breathing", "breath_1", "breath_2", "dim_once", "dim_twice")
        ),
    }
)
TEXT = vol.All(cv.string, vol.Length(min=1, max=128))
ANNOUNCE = vol.Schema(
    {
        **ANNOUNCEMENT,
        vol.Required("text"): TEXT,
        vol.Optional("effect", default="glow"): vol.In(("none", "glow", "wave")),
        vol.Optional("primary_color", default=15): COLOR,
        vol.Optional("secondary_color", default=12): COLOR,
    }
)


def get_controller(hass, data):
    entries = hass.data.get(DOMAIN, {})
    entry_id = data.get("entry_id")
    if entry_id is None:
        if len(entries) != 1:
            raise ServiceValidationError(
                "Choose entry_id when more than one Glance Clock is configured"
            )
        entry_id = next(iter(entries))
    controller = entries.get(entry_id, {}).get("apps")
    if controller is None:
        raise ServiceValidationError("Glance Clock is not loaded")
    return controller


def async_register_app_services(hass):
    async def handle(call):
        controller = get_controller(hass, call.data)
        data = call.data
        try:
            if call.service == "show_calendar":
                colors = {
                    entity: COLORS.get(color, color)
                    for entity, color in data["calendars"].items()
                }
                if any(color == 0 for color in colors.values()):
                    raise ValueError("Calendar colors must be visible (not black)")
                if not colors:
                    await controller.set_calendar([])
                    return
                now = dt_util.now()
                response = await hass.services.async_call(
                    "calendar",
                    "get_events",
                    {
                        "entity_id": list(colors),
                        "start_date_time": now.isoformat(),
                        "end_date_time": (
                            dt_util.utcnow() + timedelta(hours=12)
                        ).isoformat(),
                    },
                    blocking=True,
                    return_response=True,
                )
                await controller.set_calendar(
                    parse_events(response, colors, now.tzinfo)
                )
                if controller.hidden:
                    _LOGGER.warning(
                        "Calendar has %s events beyond the four visible bands",
                        controller.hidden,
                    )
                return
            options = {"duration": data["duration"], "sound": SOUNDS[data["sound"]]}
            if call.service == "announce_calendar":
                meeting = controller.next_meeting()
                if meeting is None:
                    return
                options.update(
                    text=meeting.title, meeting=meeting.key, effect=data["effect"]
                )
            else:
                options.update(
                    text=data["text"],
                    effect=data["effect"],
                    colors=(
                        data["primary_color"],
                        data["secondary_color"],
                    ),
                )
            controller.announce(**options)
        except (ValueError, KeyError, TypeError) as error:
            # Do not include calendar titles or provider response payloads in logs/errors.
            raise ServiceValidationError(
                "Invalid or unavailable app data; check entity selection, colors and scene size"
            ) from error

    for name, schema in zip(
        APP_SERVICES, (CALENDAR, CALENDAR_NOTICE, ANNOUNCE)
    ):
        hass.services.async_register(DOMAIN, name, handle, schema=schema)


def async_unregister_app_services(hass):
    for name in APP_SERVICES:
        hass.services.async_remove(DOMAIN, name)
