"""Bluetooth coordinator for passive device detection."""
import logging
from homeassistant.core import HomeAssistant
from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)

_LOGGER = logging.getLogger(__name__)


def create_passive_coordinator(
    hass: HomeAssistant,
    mac_address: str,
) -> PassiveBluetoothProcessorCoordinator:
    """Create a passive Bluetooth coordinator for device detection.

    This coordinator is used for device presence detection and doesn't
    actively poll the device. It relies on Bluetooth advertisements.

    Args:
        hass: Home Assistant instance
        mac_address: MAC address of the device to monitor

    Returns:
        Configured PassiveBluetoothProcessorCoordinator
    """

    def _simple_update_method(service_info):
        """Simple update method for device detection.

        This is a no-op since we're only using the coordinator for
        device presence detection, not data processing.

        Args:
            service_info: Bluetooth service info from advertisement

        Returns:
            None (no data to process)
        """
        return None

    coordinator = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=mac_address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=_simple_update_method,
        connectable=True,
    )

    _LOGGER.debug(f"Created passive Bluetooth coordinator for {mac_address}")

    return coordinator
