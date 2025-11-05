"""Sensor platform for Glance Clock."""
import logging
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components import bluetooth
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Standard Bluetooth Battery Service UUID
BATTERY_SERVICE_UUID = "0000180f-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL_CHARACTERISTIC_UUID = "00002a19-0000-1000-8000-00805f9b34fb"

# Standard Bluetooth Device Information Service UUIDs
DEVICE_INFO_SERVICE_UUID = "0000180a-0000-1000-8000-00805f9b34fb"
MANUFACTURER_NAME_CHAR_UUID = "00002a29-0000-1000-8000-00805f9b34fb"
MODEL_NUMBER_CHAR_UUID = "00002a24-0000-1000-8000-00805f9b34fb"
SERIAL_NUMBER_CHAR_UUID = "00002a25-0000-1000-8000-00805f9b34fb"
HARDWARE_REVISION_CHAR_UUID = "00002a27-0000-1000-8000-00805f9b34fb"
FIRMWARE_REVISION_CHAR_UUID = "00002a26-0000-1000-8000-00805f9b34fb"
SOFTWARE_REVISION_CHAR_UUID = "00002a28-0000-1000-8000-00805f9b34fb"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glance Clock sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    mac_address = data["mac_address"]
    name = data["name"]
    connection_manager = data.get("connection_manager")

    entities = []

    # Add battery sensor
    battery_sensor = GlanceClockBatterySensor(
        mac_address, name, connection_manager, entry
    )
    entities.append(battery_sensor)

    async_add_entities(entities)
    _LOGGER.info(f"✅ Added {len(entities)} sensor entities for {name}")


class GlanceClockBatterySensor(SensorEntity):
    """Battery sensor for Glance Clock."""

    def __init__(self, mac_address: str, device_name: str, connection_manager, entry: ConfigEntry):
        """Initialize the battery sensor."""
        self._mac_address = mac_address
        self._device_name = device_name
        self._connection_manager = connection_manager
        self._entry = entry
        self._attr_name = f"{device_name} Battery"
        self._attr_unique_id = f"{mac_address}_battery"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_icon = "mdi:battery"
        self._battery_level = None
        self._available = False

        # Device info - start with minimal info, will be populated from Bluetooth
        self._device_manufacturer = None
        self._device_model = None
        self._device_sw_version = None
        self._device_hw_version = None
        self._device_serial_number = None
        self._device_info_read = False  # Track if we've attempted to read device info

        # Set up Bluetooth service info callback
        self._cancel_callback = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        device_info = DeviceInfo(
            identifiers={(DOMAIN, self._mac_address)},
            name=self._device_name,
            manufacturer=self._device_manufacturer or "Glance",
            model=self._device_model or "Clock",
            connections={("bluetooth", self._mac_address)},
        )

        # Add optional fields if available
        if self._device_sw_version:
            device_info["sw_version"] = self._device_sw_version
        if self._device_hw_version:
            device_info["hw_version"] = self._device_hw_version
        if self._device_serial_number:
            device_info["serial_number"] = self._device_serial_number

        return device_info

    @property
    def native_value(self):
        """Return the battery level."""
        return self._battery_level

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._available and self._battery_level is not None

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Register for Bluetooth service info updates
        self._cancel_callback = bluetooth.async_register_callback(
            self.hass,
            self._handle_bluetooth_event,
            {"address": self._mac_address},
            bluetooth.BluetoothScanningMode.ACTIVE,
        )

        # Register callback with connection manager to immediately read device info when connected
        if self._connection_manager:
            self._connection_manager.add_connection_callback(
                self._on_connection_established)

        # Create initial device registry entry with basic info
        # This ensures the device appears immediately, even if not connected
        await self._create_or_update_device_registry()

        # Try to read device info and battery level immediately if already connected
        await self._update_device_info()
        await self._update_battery_level()

        _LOGGER.info(f"🔋 Battery sensor added for {self._device_name}")

    async def _on_connection_established(self) -> None:
        """Called when connection manager establishes a connection."""
        _LOGGER.info(
            f"🔗 Connection established for {self._device_name} - reading device info immediately")

        # Read device information immediately upon connection
        await self._update_device_info()
        await self._update_battery_level()

    async def _create_or_update_device_registry(self) -> None:
        """Create or update device registry entry."""
        try:
            device_registry = dr.async_get(self.hass)

            # Create or update the device entry
            device_registry.async_get_or_create(
                config_entry_id=self._entry.entry_id,
                identifiers={(DOMAIN, self._mac_address)},
                connections={("bluetooth", self._mac_address)},
                name=self._device_name,
                manufacturer=self._device_manufacturer or "Glance",
                model="Clock Clock",
                model_id=self._device_model,
                sw_version=self._device_sw_version,
                hw_version=self._device_hw_version,
                serial_number=self._device_serial_number,
            )

            _LOGGER.debug(
                f"✅ Created/updated device registry for {self._device_name}")
        except Exception as e:
            _LOGGER.error(f"❌ Failed to create/update device registry: {e}")

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        # Remove connection callback
        if self._connection_manager:
            self._connection_manager.remove_connection_callback(
                self._on_connection_established)

        if self._cancel_callback:
            self._cancel_callback()
        await super().async_will_remove_from_hass()

    async def _update_device_info(self) -> None:
        """Update device information via active connection."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.debug(
                f"ℹ️ No active connection for device info reading on {self._device_name}")
            return

        try:
            client = self._connection_manager.client
            if not client or not client.is_connected:
                return

            # Check if device information service is available
            services = client.services
            device_info_service = None

            for service in services:
                if service.uuid.lower() == DEVICE_INFO_SERVICE_UUID.lower():
                    device_info_service = service
                    break

            if not device_info_service:
                _LOGGER.debug(
                    f"ℹ️ No device information service found on {self._device_name}")
                return

            _LOGGER.info(
                f"ℹ️ Reading device information for {self._device_name}")

            # Read various device information characteristics
            # Note: Only use FIRMWARE_REVISION for sw_version, not SOFTWARE_REVISION
            # SOFTWARE_REVISION contains raw hex data that should not be displayed
            device_info_chars = {
                MANUFACTURER_NAME_CHAR_UUID: "_device_manufacturer",
                MODEL_NUMBER_CHAR_UUID: "_device_model",
                SERIAL_NUMBER_CHAR_UUID: "_device_serial_number",
                HARDWARE_REVISION_CHAR_UUID: "_device_hw_version",
                FIRMWARE_REVISION_CHAR_UUID: "_device_sw_version",
            }

            for char in device_info_service.characteristics:
                char_uuid = char.uuid.lower()
                for target_uuid, attr_name in device_info_chars.items():
                    if char_uuid == target_uuid.lower():
                        try:
                            data = await client.read_gatt_char(char.uuid)
                            if data:
                                # Decode as UTF-8 string
                                value = data.decode('utf-8').strip('\x00')
                                setattr(self, attr_name, value)
                                _LOGGER.info(f"ℹ️ {attr_name}: {value}")
                        except Exception as e:
                            _LOGGER.debug(
                                f"ℹ️ Could not read {attr_name}: {e}")

            # Update device registry with new info
            await self._create_or_update_device_registry()

            # Mark that we've successfully read device info
            self._device_info_read = True

            self.async_write_ha_state()

        except Exception as e:
            _LOGGER.debug(
                f"ℹ️ Could not read device information for {self._device_name}: {e}")
            # This is expected if the device doesn't support device info service

    @callback
    def _handle_bluetooth_event(
        self, service_info: bluetooth.BluetoothServiceInfoBleak, change: bluetooth.BluetoothChange
    ) -> None:
        """Handle Bluetooth events."""
        _LOGGER.debug(f"🔋 Bluetooth event for {self._device_name}: {change}")

        # Check if we have battery service data in the advertisement
        if service_info.advertisement.service_data:
            # Look for battery service UUID in service data
            for uuid, data in service_info.advertisement.service_data.items():
                if uuid.lower() == BATTERY_SERVICE_UUID.lower():
                    if data and len(data) > 0:
                        # First byte is typically the battery level
                        battery_level = data[0]
                        if 0 <= battery_level <= 100:
                            self._battery_level = battery_level
                            self._available = True
                            self.async_write_ha_state()
                            _LOGGER.info(
                                f"🔋 Battery level from advertisement: {battery_level}%")
                            return

        # Check if we have manufacturer data that might contain battery info
        if service_info.advertisement.manufacturer_data:
            for manufacturer_id, data in service_info.advertisement.manufacturer_data.items():
                # This is device-specific - you might need to adjust based on Glance Clock's format
                if len(data) >= 2:
                    # Some devices put battery level in manufacturer data
                    # You'll need to check Glance Clock's specific format
                    _LOGGER.debug(
                        f"🔋 Manufacturer data from {manufacturer_id}: {data.hex()}")

        # If no battery info in advertisement, try active connection
        self.hass.async_create_task(self._update_battery_level())

    async def _update_battery_level(self) -> None:
        """Update battery level via active connection."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.debug(
                f"🔋 No active connection for battery reading on {self._device_name}")
            return

        try:
            client = self._connection_manager.client
            if not client or not client.is_connected:
                return

            # Check if battery service is available
            services = client.services
            battery_service = None

            for service in services:
                if service.uuid.lower() == BATTERY_SERVICE_UUID.lower():
                    battery_service = service
                    break

            if not battery_service:
                _LOGGER.debug(
                    f"🔋 No battery service found on {self._device_name}")
                return

            # Find battery level characteristic
            battery_char = None
            for char in battery_service.characteristics:
                if char.uuid.lower() == BATTERY_LEVEL_CHARACTERISTIC_UUID.lower():
                    battery_char = char
                    break

            if not battery_char:
                _LOGGER.debug(
                    f"🔋 No battery level characteristic found on {self._device_name}")
                return

            # Read battery level
            battery_data = await client.read_gatt_char(battery_char.uuid)
            if battery_data and len(battery_data) > 0:
                battery_level = battery_data[0]
                if 0 <= battery_level <= 100:
                    self._battery_level = battery_level
                    self._available = True
                    self.async_write_ha_state()
                    _LOGGER.info(
                        f"🔋 Battery level read via GATT: {battery_level}%")
                else:
                    _LOGGER.warning(
                        f"🔋 Invalid battery level: {battery_level}")

        except Exception as e:
            _LOGGER.debug(
                f"🔋 Could not read battery level for {self._device_name}: {e}")
            # This is expected if the device doesn't support battery service

    async def async_update(self) -> None:
        """Update the sensor."""
        await self._update_battery_level()

        # Update device info only if we haven't successfully read it yet
        if not self._device_info_read:
            await self._update_device_info()
