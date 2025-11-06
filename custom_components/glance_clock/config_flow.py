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

from .const import DOMAIN, GLANCE_SERVICE_UUID

_LOGGER = logging.getLogger(__name__)

# Connection test constants
CONNECTION_TEST_TIMEOUT = 15.0
CONNECTION_TEST_MAX_ATTEMPTS = 2

# Device name patterns for identification
DEVICE_NAME_PATTERNS = ("glance", "clock")


class GlanceClockConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Glance Clock."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._device_name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle the bluetooth discovery step."""
        _LOGGER.info(
            "Bluetooth discovery for device: %s (%s)",
            discovery_info.name,
            discovery_info.address
        )

        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        if not self._is_glance_device(discovery_info):
            return self.async_abort(reason="not_supported")

        self._discovery_info = discovery_info
        self._device_name = discovery_info.name or discovery_info.address

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm Bluetooth discovery."""
        assert self._discovery_info is not None

        if user_input is not None:
            try:
                await self._test_connection()
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

        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._device_name or "Glance Clock"},
        )

    async def _test_connection(self) -> None:
        """Test basic BLE connection to validate device is accessible."""
        assert self._discovery_info is not None

        ble_device = async_ble_device_from_address(
            self.hass, self._discovery_info.address, connectable=True
        )

        if ble_device is None:
            raise BleakError("Device not found")

        client = None
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self._device_name or "Glance Clock",
                max_attempts=CONNECTION_TEST_MAX_ATTEMPTS,
                timeout=CONNECTION_TEST_TIMEOUT,
                use_services_cache=False,
            )

            if not client or not client.is_connected:
                raise BleakError("Failed to establish connection")

            # Verify device services
            self._verify_device_services(client)

        except BleakError:
            raise
        except Exception as ex:
            _LOGGER.error("Connection test failed: %s", ex)
            raise BleakError(f"Connection error: {ex}")
        finally:
            if client and client.is_connected:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    def _verify_device_services(self, client: BleakClientWithServiceCache) -> None:
        """Verify the device has expected Glance services."""
        try:
            services = client.services
            _LOGGER.debug("Discovered %d services", len(services.services))
            
            # Extract UUID prefix from GLANCE_SERVICE_UUID for matching
            service_uuid_prefix = GLANCE_SERVICE_UUID.split('-')[0].lower()
            
            glance_services = [
                s for s in services.services.values()
                if service_uuid_prefix in str(s.uuid).lower()
            ]
            
            if glance_services:
                _LOGGER.debug("Found Glance service - device validated")
            else:
                _LOGGER.warning("No Glance service found, but proceeding")
        except Exception as ex:
            _LOGGER.debug("Service discovery had issues: %s", ex)

    def _is_glance_device(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Check if this is a Glance Clock device."""
        # Check device name patterns
        if service_info.name and self._matches_device_name(service_info.name):
            _LOGGER.debug("Device identified by name: %s", service_info.name)
            return True

        # Check for service UUIDs
        if self._has_glance_service(service_info.service_uuids):
            _LOGGER.debug("Device identified by service UUID")
            return True

        return False

    def _matches_device_name(self, name: str) -> bool:
        """Check if device name matches Glance Clock patterns."""
        name_lower = name.lower()
        return any(pattern in name_lower for pattern in DEVICE_NAME_PATTERNS)

    def _has_glance_service(self, service_uuids: list[str]) -> bool:
        """Check if device has Glance service UUID."""
        service_uuid_prefix = GLANCE_SERVICE_UUID.split('-')[0].lower()
        return any(service_uuid_prefix in uuid.lower() for uuid in service_uuids)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the user step to pick discovered device."""
        if user_input is not None:
            address = user_input["address"]
            discovery_info = self._find_device_by_address(address)
            
            if discovery_info:
                self._discovery_info = discovery_info
                self._device_name = discovery_info.name or discovery_info.address
                return await self.async_step_bluetooth_confirm()
            
            return self.async_abort(reason="device_not_found")

        # Scan for available devices
        devices = self._get_available_devices()

        if not devices:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("address"): vol.In(devices)
            }),
        )

    def _find_device_by_address(
        self, address: str
    ) -> BluetoothServiceInfoBleak | None:
        """Find a Glance device by address in discovered devices."""
        for info in async_discovered_service_info(self.hass):
            if info.address == address and self._is_glance_device(info):
                return info
        return None

    def _get_available_devices(self) -> dict[str, str]:
        """Get dictionary of available Glance Clock devices."""
        current_addresses = self._async_current_ids()
        devices = {}

        for info in async_discovered_service_info(self.hass):
            if info.address in current_addresses:
                continue

            if self._is_glance_device(info):
                device_name = info.name or f"Glance Clock {info.address[-5:]}"
                devices[info.address] = f"{device_name} ({info.address})"

        _LOGGER.info("Found %d available Glance Clock device(s)", len(devices))
        return devices
