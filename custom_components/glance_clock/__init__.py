"""Initialize the Glance Clock integration."""
import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache

from .const import (
    DOMAIN,
    GLANCE_CHARACTERISTIC_UUID,
)
from .services import (
    handle_update_display_settings,
    handle_read_current_settings,
    handle_refresh_entities,
    handle_send_notice,
    handle_send_forecast,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NOTIFY, Platform.SENSOR,
             Platform.SWITCH, Platform.LIGHT, Platform.SELECT]


class GlanceClockConnectionManager:
    """Manages active connection to Glance Clock."""

    def __init__(self, hass: HomeAssistant, mac_address: str, name: str):
        self.hass = hass
        self.mac_address = mac_address
        self.name = name
        self.client = None
        self._connection_task = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._is_connecting = False
        self._connection_callbacks = []

    def add_connection_callback(self, callback):
        """Add a callback to be called when connection is established."""
        self._connection_callbacks.append(callback)

    def remove_connection_callback(self, callback):
        """Remove a connection callback."""
        if callback in self._connection_callbacks:
            self._connection_callbacks.remove(callback)

    async def _notify_connection_callbacks(self):
        """Notify all registered callbacks about connection."""
        _LOGGER.debug(
            f"Notifying {len(self._connection_callbacks)} connection callbacks")
        for callback in self._connection_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                _LOGGER.error(f"Error in connection callback: {e}")

    @property
    def is_connected(self) -> bool:
        """Return True if connected."""
        return self.client is not None and self.client.is_connected

    async def start_connection(self):
        """Start maintaining an active connection."""
        if self._connection_task:
            return

        _LOGGER.debug(f"Starting connection manager for {self.name}")
        self._connection_task = asyncio.create_task(
            self._maintain_connection())

    async def stop_connection(self):
        """Stop the connection manager."""
        if self._connection_task:
            self._connection_task.cancel()
            try:
                await self._connection_task
            except asyncio.CancelledError:
                pass
            self._connection_task = None

        if self.client and self.client.is_connected:
            await self.client.disconnect()
            self.client = None

        _LOGGER.debug(f"Connection manager stopped for {self.name}")

    async def _maintain_connection(self):
        """Maintain an active connection with automatic reconnection."""
        while True:
            try:
                if not self.client or not self.client.is_connected:
                    if not self._is_connecting:
                        await self._connect()

                # Check connection every 60 seconds
                await asyncio.sleep(60)

                # Ping the connection
                if self.client and self.client.is_connected:
                    try:
                        await self.client.read_gatt_char(GLANCE_CHARACTERISTIC_UUID)
                        self._reconnect_attempts = 0
                    except Exception as e:
                        _LOGGER.warning(
                            f"Connection ping failed for {self.name}: {e}")
                        await self._disconnect()

            except asyncio.CancelledError:
                break
            except Exception as e:
                _LOGGER.error(f"Connection maintenance error: {e}")
                await asyncio.sleep(30)

    async def _connect(self):
        """Establish connection."""
        if self._is_connecting:
            return

        self._is_connecting = True

        try:
            _LOGGER.debug(f"Connecting to {self.name} ({self.mac_address})")

            # Get BLE device
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.mac_address, connectable=True
            )

            if not ble_device:
                service_infos = bluetooth.async_discovered_service_info(
                    self.hass, connectable=True)
                for service_info in service_infos:
                    if service_info.device.address.upper() == self.mac_address.upper():
                        ble_device = service_info.device
                        break

            if not ble_device:
                raise Exception(f"Device {self.mac_address} not reachable")

            # Establish connection
            def get_ble_device():
                device = bluetooth.async_ble_device_from_address(
                    self.hass, ble_device.address, connectable=True
                )
                return device or ble_device

            self.client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self.name,
                disconnected_callback=self._on_disconnect,
                max_attempts=3,
                timeout=30.0,
                use_services_cache=True,
                ble_device_callback=get_ble_device,
            )

            if self.client and self.client.is_connected:
                _LOGGER.debug(f"Connected to {self.name}")
                self._reconnect_attempts = 0
                await self._notify_connection_callbacks()
            else:
                raise Exception("Failed to establish connection")

        except Exception as e:
            self._reconnect_attempts += 1
            _LOGGER.error(
                f"Connection failed (attempt {self._reconnect_attempts}): {e}")

            if self._reconnect_attempts < self._max_reconnect_attempts:
                await asyncio.sleep(30 * self._reconnect_attempts)
            else:
                _LOGGER.error(
                    f"Max reconnection attempts reached for {self.name}")
                await asyncio.sleep(300)  # 5 minutes
                self._reconnect_attempts = 0

        finally:
            self._is_connecting = False

    async def _disconnect(self):
        """Disconnect from device."""
        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None

    def _on_disconnect(self, client):
        """Handle disconnect callback."""
        _LOGGER.warning(f"{self.name} disconnected unexpectedly")
        self.client = None

    async def send_command(self, command_data: bytes) -> bool:
        """Send a command using the active connection."""
        if not self.client or not self.client.is_connected:
            _LOGGER.warning(
                f"No active connection to {self.name}, attempting to connect")
            await self._connect()

            if not self.client or not self.client.is_connected:
                _LOGGER.error("Failed to establish connection for command")
                return False

        try:
            # Try write with response first
            try:
                await self.client.write_gatt_char(
                    GLANCE_CHARACTERISTIC_UUID,
                    command_data,
                    response=True
                )
            except Exception:
                # Fallback to write without response
                await self.client.write_gatt_char(
                    GLANCE_CHARACTERISTIC_UUID,
                    command_data,
                    response=False
                )

            return True

        except Exception as e:
            _LOGGER.error(f"Failed to send command: {e}")
            await self._disconnect()
            return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Glance Clock integration."""
    hass.data.setdefault(DOMAIN, {})

    # Get data from config entry
    mac_address = entry.data.get("mac_address") or entry.data.get("address")
    name = entry.data.get("name", "Glance Clock")

    if not mac_address:
        _LOGGER.error("MAC address is required but not found in configuration")
        return False

    _LOGGER.info(
        f"Setting up Glance Clock integration for {name} ({mac_address})")

    # Create active connection manager
    connection_manager = GlanceClockConnectionManager(hass, mac_address, name)
    await connection_manager.start_connection()

    # Create Bluetooth coordinator for device detection
    def _simple_update_method(service_info):
        """Simple update method for device detection."""
        return None

    coordinator = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=mac_address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=_simple_update_method,
        connectable=True,
    )

    # Store config data
    hass.data[DOMAIN][entry.entry_id] = {
        "mac_address": mac_address,
        "name": name,
        "coordinator": coordinator,
        "connection_manager": connection_manager,
    }

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start coordinator
    entry.async_on_unload(coordinator.async_start())

    # Register services
    async def _handle_update_display_settings(call):
        await handle_update_display_settings(hass, entry.entry_id, call)

    async def _handle_read_current_settings(call):
        await handle_read_current_settings(hass, entry.entry_id, call)

    async def _handle_refresh_entities(call):
        await handle_refresh_entities(hass, entry.entry_id, call)

    async def _handle_send_notice(call):
        await handle_send_notice(hass, entry.entry_id, call)

    async def _handle_send_forecast(call):
        await handle_send_forecast(hass, entry.entry_id, call)

    hass.services.async_register(
        DOMAIN, "update_display_settings", _handle_update_display_settings)
    hass.services.async_register(
        DOMAIN, "read_current_settings", _handle_read_current_settings)
    hass.services.async_register(
        DOMAIN, "refresh_entities", _handle_refresh_entities)
    hass.services.async_register(DOMAIN, "send_notice", _handle_send_notice)
    hass.services.async_register(
        DOMAIN, "send_forecast", _handle_send_forecast)

    _LOGGER.info(f"Glance Clock integration setup complete for {name}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    # Stop the connection manager
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    connection_manager = entry_data.get("connection_manager")

    if connection_manager:
        await connection_manager.stop_connection()

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up stored data
    hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
