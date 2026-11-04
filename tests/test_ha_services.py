"""Optional HA schema and action-handler tests (install HA to run)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("homeassistant.core")
from homeassistant.core import ServiceCall, State, SupportsResponse
from homeassistant.exceptions import ServiceValidationError

from custom_components.glance_clock.apps.services import async_register_app_services


def setup(tmp_path):
    handlers = {}
    states = {}

    def register(domain, name, handler, schema=None, **kwargs):
        handlers[(domain, name)] = (handler, schema)

    async def call(domain, name, data, **kwargs):
        handler, schema = handlers[(domain, name)]
        return await handler(
            ServiceCall(hass, domain, name, schema(data) if schema else data)
        )

    hass = SimpleNamespace(
        data={},
        services=SimpleNamespace(async_register=register, async_call=call),
        states=SimpleNamespace(
            get=states.get,
            async_set=lambda entity, value, attrs=None: states.update(
                {entity: State(entity, value, attrs)}
            ),
        ),
    )
    apps = SimpleNamespace(set_calendar=AsyncMock(), announce=Mock(), hidden=0)
    hass.data["glance_clock"] = {"one": {"apps": apps}}
    async_register_app_services(hass)
    return hass, apps


@pytest.mark.asyncio
async def test_calendar_uses_events_api_not_next_event_attribute(tmp_path):
    hass, apps = setup(tmp_path)

    async def get_events(call):
        assert call.data["entity_id"] == ["calendar.family"]
        return {
            "calendar.family": {
                "events": [
                    {
                        "start": "2026-10-14T16:00:00-04:00",
                        "end": "2026-10-14T20:00:00-04:00",
                        "summary": "Dance",
                    }
                ]
            }
        }

    hass.services.async_register(
        "calendar", "get_events", get_events, supports_response=SupportsResponse.ONLY
    )
    await hass.services.async_call(
        "glance_clock",
        "show_calendar",
        {"calendars": {"calendar.family": "blue_violet"}},
        blocking=True,
    )
    meeting = apps.set_calendar.call_args.args[0][0]
    assert meeting.title == "Dance" and meeting.color == 11


@pytest.mark.asyncio
async def test_multiple_clocks_require_explicit_selection(tmp_path):
    hass, apps = setup(tmp_path)
    other = SimpleNamespace(announce=Mock())
    hass.data["glance_clock"]["two"] = {"apps": other}
    with pytest.raises(ServiceValidationError, match="entry_id"):
        await hass.services.async_call(
            "glance_clock", "announce", {"text": "Hello"}, blocking=True
        )
    await hass.services.async_call(
        "glance_clock", "announce", {"entry_id": "two", "text": "Hello"}, blocking=True
    )
    apps.announce.assert_not_called()
    other.announce.assert_called_once()
