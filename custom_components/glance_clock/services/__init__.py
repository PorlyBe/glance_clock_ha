"""Service management for Glance Clock integration."""
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry

from ..const import DOMAIN
from .display_settings import handle_update_display_settings, handle_read_current_settings
from .refresh import handle_refresh_entities
from .notice import handle_send_notice
from .forecast import handle_send_forecast
from .timer import handle_send_timer

_LOGGER = logging.getLogger(__name__)


async def async_register_services(hass: HomeAssistant, entry: ConfigEntry):
    """Register all services for the integration."""

    async def _handle_update_display_settings(call: ServiceCall):
        await handle_update_display_settings(hass, entry, call)

    async def _handle_read_current_settings(call: ServiceCall):
        await handle_read_current_settings(hass, entry, call)

    async def _handle_refresh_entities(call: ServiceCall):
        await handle_refresh_entities(hass, entry, call)

    async def _handle_send_notice(call: ServiceCall):
        await handle_send_notice(hass, entry, call)

    async def _handle_send_forecast(call: ServiceCall):
        await handle_send_forecast(hass, entry, call)

    async def _handle_send_timer(call: ServiceCall):
        await handle_send_timer(hass, entry, call)

    # Register services
    hass.services.async_register(
        DOMAIN, "update_display_settings", _handle_update_display_settings
    )
    hass.services.async_register(
        DOMAIN, "read_current_settings", _handle_read_current_settings
    )
    hass.services.async_register(
        DOMAIN, "refresh_entities", _handle_refresh_entities
    )
    hass.services.async_register(
        DOMAIN, "send_notice", _handle_send_notice
    )
    hass.services.async_register(
        DOMAIN, "send_forecast", _handle_send_forecast
    )
    hass.services.async_register(
        DOMAIN, "send_timer", _handle_send_timer
    )

    _LOGGER.info("All Glance Clock services registered")


async def async_unregister_services(hass: HomeAssistant):
    """Unregister all services for the integration."""
    # Only unregister if this is the last config entry
    if len(hass.data.get(DOMAIN, {})) <= 1:
        hass.services.async_remove(DOMAIN, "update_display_settings")
        hass.services.async_remove(DOMAIN, "read_current_settings")
        hass.services.async_remove(DOMAIN, "refresh_entities")
        hass.services.async_remove(DOMAIN, "send_notice")
        hass.services.async_remove(DOMAIN, "send_forecast")
        hass.services.async_remove(DOMAIN, "send_timer")
        _LOGGER.info("All Glance Clock services unregistered")
