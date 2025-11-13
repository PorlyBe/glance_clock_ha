"""Entity refresh service for Glance Clock."""
import logging
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)


async def handle_refresh_entities(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Handle refreshing entity states."""
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entities = hass.helpers.entity_registry.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    )

    for entity_entry in entities:
        entity_id = entity_entry.entity_id
        await hass.helpers.entity_component.async_update_entity(hass, entity_id)
