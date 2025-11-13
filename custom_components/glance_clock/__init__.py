"""Initialize the Glance Clock integration."""
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN
from .bluetooth import GlanceClockConnectionManager, create_passive_coordinator
from .services import async_register_services, async_unregister_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.NOTIFY,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Glance Clock integration from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry for this integration instance

    Returns:
        True if setup was successful
    """
    hass.data.setdefault(DOMAIN, {})

    # Extract configuration
    mac_address = entry.data.get("mac_address") or entry.data.get("address")
    name = entry.data.get("name", "Glance Clock")

    if not mac_address:
        _LOGGER.error("MAC address is required but not found in configuration")
        return False

    _LOGGER.info(
        f"Setting up Glance Clock integration for {name} ({mac_address})")

    # Create and start active connection manager
    connection_manager = GlanceClockConnectionManager(hass, mac_address, name)
    await connection_manager.start_connection()

    # Create passive Bluetooth coordinator for device detection
    coordinator = create_passive_coordinator(hass, mac_address)

    # Store integration data
    hass.data[DOMAIN][entry.entry_id] = {
        "mac_address": mac_address,
        "name": name,
        "coordinator": coordinator,
        "connection_manager": connection_manager,
    }

    # Set up platforms (entities)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start coordinator and ensure cleanup on unload
    entry.async_on_unload(coordinator.async_start())

    # Register integration services
    await async_register_services(hass, entry)

    _LOGGER.info(f"Glance Clock integration setup complete for {name}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry being unloaded

    Returns:
        True if unload was successful
    """
    # Stop the connection manager
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    connection_manager = entry_data.get("connection_manager")

    if connection_manager:
        _LOGGER.debug(
            f"Stopping connection manager for {entry_data.get('name')}")
        await connection_manager.stop_connection()

    # Unload all platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up stored data
    hass.data[DOMAIN].pop(entry.entry_id, None)

    # Unregister services if this is the last entry
    await async_unregister_services(hass)

    _LOGGER.info(
        f"Glance Clock integration unloaded for {entry_data.get('name')}")

    return unload_ok
