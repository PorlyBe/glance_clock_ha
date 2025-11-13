"""Bluetooth connection management for Glance Clock."""
import logging
import asyncio
from homeassistant.core import HomeAssistant
from homeassistant.components import bluetooth
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache

from ..const import GLANCE_CHARACTERISTIC_UUID

_LOGGER = logging.getLogger(__name__)


class GlanceClockConnectionManager:
    """Manages active BLE connection to Glance Clock with automatic reconnection."""

    def __init__(self, hass: HomeAssistant, mac_address: str, name: str):
        """Initialize the connection manager.

        Args:
            hass: Home Assistant instance
            mac_address: MAC address of the Glance Clock device
            name: Friendly name for the device
        """
        self.hass = hass
        self.mac_address = mac_address
        self.name = name
        self.client = None
        self._connection_task = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        self._is_connecting = False
        self._connection_callbacks = []
        self._cached_settings = None
        self._settings_read_time = None

    # Callback Management

    def add_connection_callback(self, callback):
        """Add a callback to be called when connection is established.

        Args:
            callback: Async or sync function to call on connection
        """
        self._connection_callbacks.append(callback)

    def remove_connection_callback(self, callback):
        """Remove a connection callback.

        Args:
            callback: The callback to remove
        """
        if callback in self._connection_callbacks:
            self._connection_callbacks.remove(callback)

    async def _notify_connection_callbacks(self):
        """Notify all registered callbacks about successful connection."""
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

    # Settings Cache Management

    def get_cached_settings(self):
        """Get cached settings if available and fresh (< 60 seconds old).

        Returns:
            Cached settings dict or None if cache is stale/empty
        """
        import time
        if self._cached_settings and self._settings_read_time:
            if time.time() - self._settings_read_time < 60:
                return self._cached_settings
        return None

    def cache_settings(self, settings):
        """Cache settings with current timestamp.

        Args:
            settings: Settings dict to cache
        """
        import time
        self._cached_settings = settings
        self._settings_read_time = time.time()

    def clear_settings_cache(self):
        """Clear cached settings."""
        self._cached_settings = None
        self._settings_read_time = None

    # Connection State

    @property
    def is_connected(self) -> bool:
        """Return True if actively connected to device."""
        return self.client is not None and self.client.is_connected

    # Connection Lifecycle

    async def start_connection(self):
        """Start maintaining an active connection with automatic reconnection."""
        if self._connection_task:
            _LOGGER.debug(f"Connection task already running for {self.name}")
            return

        _LOGGER.debug(f"Starting connection manager for {self.name}")
        self._connection_task = asyncio.create_task(
            self._maintain_connection())

    async def stop_connection(self):
        """Stop the connection manager and disconnect from device."""
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
        """Main connection maintenance loop.

        Continuously monitors connection health and reconnects if necessary.
        Pings the device every 60 seconds to verify connection is alive.
        """
        while True:
            try:
                # Ensure we're connected
                if not self.client or not self.client.is_connected:
                    if not self._is_connecting:
                        await self._connect()

                # Wait before next health check
                await asyncio.sleep(60)

                # Ping the connection to verify it's still alive
                if self.client and self.client.is_connected:
                    try:
                        await self.client.read_gatt_char(GLANCE_CHARACTERISTIC_UUID)
                        self._reconnect_attempts = 0
                    except Exception as e:
                        _LOGGER.warning(
                            f"Connection ping failed for {self.name}: {e}")
                        await self._disconnect()

            except asyncio.CancelledError:
                _LOGGER.debug(
                    f"Connection maintenance cancelled for {self.name}")
                break
            except Exception as e:
                _LOGGER.error(
                    f"Connection maintenance error for {self.name}: {e}")
                await asyncio.sleep(30)

    async def _connect(self):
        """Establish BLE connection to the device.

        Uses exponential backoff for retry attempts.
        """
        if self._is_connecting:
            _LOGGER.debug(f"Already connecting to {self.name}")
            return

        self._is_connecting = True

        try:
            _LOGGER.debug(f"Connecting to {self.name} ({self.mac_address})")

            # Try to get BLE device from Home Assistant's Bluetooth integration
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self.mac_address, connectable=True)

            # If not found, search through discovered devices
            if not ble_device:
                _LOGGER.debug(
                    f"Device not in cache, searching discovered devices")
                service_infos = bluetooth.async_discovered_service_info(
                    self.hass, connectable=True)
                for service_info in service_infos:
                    if service_info.device.address.upper() == self.mac_address.upper():
                        ble_device = service_info.device
                        _LOGGER.debug(f"Found device in discovered services")
                        break

            if not ble_device:
                raise Exception(f"Device {self.mac_address} not reachable")

            # Callback to get fresh BLE device for connection
            def get_ble_device():
                device = bluetooth.async_ble_device_from_address(
                    self.hass, ble_device.address, connectable=True
                )
                return device or ble_device

            # Establish connection with retry logic
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
                _LOGGER.info(f"Successfully connected to {self.name}")
                self._reconnect_attempts = 0
                await self._notify_connection_callbacks()
            else:
                raise Exception("Failed to establish connection")

        except Exception as e:
            self._reconnect_attempts += 1
            _LOGGER.error(
                f"Connection failed to {self.name} (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}): {e}")

            # Exponential backoff for reconnection attempts
            if self._reconnect_attempts < self._max_reconnect_attempts:
                wait_time = 30 * self._reconnect_attempts
                _LOGGER.debug(f"Waiting {wait_time}s before retry")
                await asyncio.sleep(wait_time)
            else:
                _LOGGER.warning(
                    f"Max reconnection attempts reached for {self.name}, waiting 5 minutes")
                # Wait 5 minutes before resetting attempts
                await asyncio.sleep(300)
                self._reconnect_attempts = 0

        finally:
            self._is_connecting = False

    async def _disconnect(self):
        """Disconnect from device and clean up client."""
        if self.client and self.client.is_connected:
            try:
                _LOGGER.debug(f"Disconnecting from {self.name}")
                await self.client.disconnect()
            except Exception as e:
                _LOGGER.debug(f"Error during disconnect: {e}")
        self.client = None

    def _on_disconnect(self, client):
        """Handle unexpected disconnection callback from Bleak.

        Args:
            client: The Bleak client that disconnected
        """
        _LOGGER.warning(f"{self.name} disconnected unexpectedly")
        self.client = None
        # Connection maintenance loop will handle reconnection

    # Command Interface

    async def send_command(self, command_data: bytes) -> bool:
        """Send a command to the device using the active connection.

        Automatically attempts to connect if not currently connected.

        Args:
            command_data: Raw bytes to send to the device

        Returns:
            True if command was sent successfully, False otherwise
        """
        # Ensure we have an active connection
        if not self.client or not self.client.is_connected:
            _LOGGER.debug(
                f"No active connection to {self.name}, attempting to connect")
            await self._connect()

            if not self.client or not self.client.is_connected:
                _LOGGER.error(
                    f"Failed to establish connection for command to {self.name}")
                return False

        try:
            # Try write with response first (more reliable)
            try:
                await self.client.write_gatt_char(
                    GLANCE_CHARACTERISTIC_UUID,
                    command_data,
                    response=True
                )
                _LOGGER.debug(f"Command sent successfully (with response)")
            except Exception as e:
                # Fallback to write without response
                _LOGGER.debug(
                    f"Write with response failed ({e}), trying without response")
                await self.client.write_gatt_char(
                    GLANCE_CHARACTERISTIC_UUID,
                    command_data,
                    response=False
                )
                _LOGGER.debug(f"Command sent successfully (without response)")

            return True

        except Exception as e:
            _LOGGER.error(f"Failed to send command to {self.name}: {e}")
            await self._disconnect()
            return False

    async def read_characteristic(self, characteristic_uuid: str | None = None) -> bytes:
        """Read data from a characteristic.

        Args:
            characteristic_uuid: UUID of characteristic to read (defaults to Glance UUID)

        Returns:
            Bytes read from the characteristic

        Raises:
            Exception if read fails or not connected
        """
        if not self.client or not self.client.is_connected:
            raise Exception(f"Not connected to {self.name}")

        uuid = characteristic_uuid if characteristic_uuid is not None else GLANCE_CHARACTERISTIC_UUID
        return await self.client.read_gatt_char(uuid)
