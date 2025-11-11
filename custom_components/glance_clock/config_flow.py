"""Config flow for Glance Clock."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_ble_device_from_address,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult


from .const import DOMAIN
from .options_flow import GlanceClockOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)


class GlanceClockConfigFlow(ConfigFlow, domain=DOMAIN):
    @staticmethod
    def async_get_options_flow(config_entry):
        return GlanceClockOptionsFlowHandler(config_entry)
    """Handle a config flow for Glance Clock."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._device_name: str | None = None
        _LOGGER.debug("Initialized GlanceClockConfigFlow")

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.info("Bluetooth discovery step for device: %s (%s)",
                     discovery_info.name, discovery_info.address)

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        # Check if this is a supported Glance Clock device
        if not self._is_glance_device(discovery_info):
            _LOGGER.warning(
                "Device %s is not a supported Glance Clock", discovery_info.address)
            return self.async_abort(reason="not_supported")

        self._discovery_info = discovery_info
        self._device_name = discovery_info.name or discovery_info.address

        _LOGGER.info("Glance Clock device detected: %s", self._device_name)
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm Bluetooth discovery."""
        assert self._discovery_info is not None

        _LOGGER.debug("Bluetooth confirm step, user_input: %s",
                      "provided" if user_input else "None")

        if user_input is not None:
            # Test basic BLE connection to validate device is accessible
            _LOGGER.info("Testing BLE connection for %s", self._device_name)
            try:
                await self._test_connection()
                _LOGGER.info("Connection test successful, creating config entry for %s",
                             self._device_name)
                return self.async_create_entry(
                    title=self._device_name or "Glance Clock",
                    data={
                        "address": self._discovery_info.address,
                        "name": self._device_name,
                    },
                )
            except BleakError as ex:
                _LOGGER.warning("Connection test failed: %s", ex)
                return self.async_abort(reason="cannot_connect")
            except Exception as ex:
                _LOGGER.exception("Unexpected error during connection test: %s", ex)
                return self.async_abort(reason="unknown")

        _LOGGER.debug("Showing bluetooth_confirm form for device: %s", self._device_name)
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._device_name or "Glance Clock"},
        )

    async def _test_connection(self) -> None:
        """Test basic BLE connection to validate device is accessible."""
        assert self._discovery_info is not None

        _LOGGER.debug("Testing basic connection for device: %s",
                      self._discovery_info.address)

        ble_device = async_ble_device_from_address(
            self.hass, self._discovery_info.address, connectable=True
        )

        if ble_device is None:
            raise BleakError("Device not found")

        client = None
        try:
            # Use establish_connection for basic connectivity test
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self._device_name or "Glance Clock",
                max_attempts=2,
                timeout=15.0,
                use_services_cache=False,
            )

            if client and client.is_connected:
                _LOGGER.info("Basic connection test successful")
                
                # Try to access services to verify device is responsive
                try:
                    services = client.services
                    _LOGGER.info("Discovered %d services", len(services.services))
                    
                    # Look for Glance service to confirm device type
                    glance_services = [s for s in services.services.values()
                                     if "5075f606" in str(s.uuid).lower()]
                    if glance_services:
                        _LOGGER.info("Found Glance service - device validated")
                    else:
                        _LOGGER.warning("No Glance service found, but proceeding anyway")
                        
                except Exception as service_ex:
                    _LOGGER.debug("Service discovery had issues: %s", service_ex)
                    # Don't fail on service discovery issues
            else:
                raise BleakError("Failed to establish basic connection")

        except BleakError:
            raise
        except Exception as ex:
            _LOGGER.error("Connection test failed: %s", ex)
            raise BleakError(f"Connection error: {ex}")

        finally:
            if client and client.is_connected:
                try:
                    await client.disconnect()
                    _LOGGER.debug("Disconnected after connection test")
                except Exception:
                    pass

    def _is_glance_device(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Check if this is a Glance Clock device."""
        _LOGGER.debug("Checking if device is Glance Clock: name=%s, address=%s, services=%s",
                      service_info.name, service_info.address, service_info.service_uuids)

        # Check device name patterns
        if service_info.name:
            name_lower = service_info.name.lower()
            if "glance" in name_lower or "clock" in name_lower:
                _LOGGER.debug(
                    "Device identified as Glance Clock by name: %s", service_info.name)
                return True

        # Check for service UUIDs
        for uuid in service_info.service_uuids:
            if "5075f606" in uuid.lower():  # Glance service UUID
                _LOGGER.debug(
                    "Device identified as Glance Clock by service UUID: %s", uuid)
                return True

        _LOGGER.debug("Device is not a Glance Clock")
        return False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        _LOGGER.debug("User step, user_input: %s",
                      "provided" if user_input else "None")

        if user_input is not None:
            address = user_input["address"]
            _LOGGER.info("User selected device address: %s", address)

            for info in async_discovered_service_info(self.hass):
                if info.address == address and self._is_glance_device(info):
                    _LOGGER.info(
                        "Found selected device in discovery cache: %s", info.name)
                    self._discovery_info = info
                    self._device_name = info.name or info.address
                    return await self.async_step_bluetooth_confirm()

            _LOGGER.warning(
                "Selected device %s not found or not supported", address)
            return self.async_abort(reason="device_not_found")

        # Scan for available devices
        current_addresses = self._async_current_ids()
        devices = {}

        _LOGGER.debug("Scanning for Glance Clock devices...")
        for info in async_discovered_service_info(self.hass):
            if info.address in current_addresses:
                _LOGGER.debug(
                    "Skipping already configured device: %s", info.address)
                continue

            if self._is_glance_device(info):
                device_name = info.name or f"Glance Clock {info.address[-5:]}"
                devices[info.address] = f"{device_name} ({info.address})"
                _LOGGER.debug("Found Glance Clock device: %s -> %s",
                              info.address, devices[info.address])

        _LOGGER.info("Found %d available Glance Clock devices", len(devices))

        if not devices:
            _LOGGER.warning("No Glance Clock devices found")
            return self.async_abort(reason="no_devices_found")

        schema = vol.Schema({
            vol.Required("address"): vol.In(devices)
        })

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
        )
