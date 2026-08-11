"""Number platform for Glance Clock."""
import asyncio
import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.helpers.restore_state import RestoreEntity

from .animation_state import get_animation_state
from .const import DOMAIN
from .entity import GlanceClockEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glance Clock number entities."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = entry_data["mac_address"]
    name = entry_data["name"]
    connection_manager = entry_data["connection_manager"]

    async_add_entities(
        [
            GlanceClockDndStartNumber(config_entry, mac_address, name, connection_manager),
            GlanceClockDndEndNumber(config_entry, mac_address, name, connection_manager),
            GlanceClockAnimationSpeedNumber(
                config_entry, mac_address, name, connection_manager),
        ]
    )


class GlanceClockDndHourNumber(GlanceClockEntity, NumberEntity):
    """One end of the recurring Do Not Disturb window stored on the clock.

    The window lives on the device itself, in a submessage separate from the
    permanent DND flag, so it keeps working when Home Assistant is down.
    """

    _setting_key: str

    _attr_native_min_value = 0
    _attr_native_max_value = 23
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the DND hour number."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._value = None
        self._available = False

    @property
    def native_value(self) -> float | None:
        """Return the configured hour."""
        return None if self._value is None else float(self._value)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available and self._connection_manager.is_connected

    async def async_set_native_value(self, value: float) -> None:
        """Write a new hour to the device."""
        hour = int(value)
        if not 0 <= hour <= 23:
            _LOGGER.error("DND hour must be between 0 and 23, got %s", hour)
            return

        if await self._write_settings({self._setting_key: hour}):
            self._value = hour
            self.async_write_ha_state()
            _LOGGER.info("%s set to %02d:00", self.name, hour)
        else:
            _LOGGER.error("Failed to set %s", self.name)

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()

        if self._connection_manager:
            self._connection_manager.add_connection_callback(self._on_connection_established)

        await self._update_initial_state()

    async def _on_connection_established(self) -> None:
        """Called when connection manager establishes a connection."""
        _LOGGER.debug("🔗 Connection established for %s - reading state immediately", self.name)
        await self.async_update()
        self.async_write_ha_state()

    async def _update_initial_state(self) -> None:
        """Update initial state in background to avoid blocking startup."""
        try:
            if not self._connection_manager.is_connected:
                await asyncio.sleep(2)
            await self.async_update()
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.debug("Could not read initial state for %s: %s", self.name, e)

    async def async_update(self) -> None:
        """Update the value from the device."""
        try:
            settings = await self._read_settings()
            # A device with no schedule at all reports None, which is not the
            # same as midnight -- leave the entity unknown rather than showing
            # a zero the user never set.
            if settings and settings.get(self._setting_key) is not None:
                self._value = settings[self._setting_key]
                self._available = True
            else:
                self._available = self._connection_manager.is_connected
        except Exception as e:
            _LOGGER.debug("Error updating %s: %s", self.name, e)
            self._available = self._connection_manager.is_connected


class GlanceClockDndStartNumber(GlanceClockDndHourNumber):
    """Hour the quiet period starts."""

    _setting_key = "dndFromHour"

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the DND start hour."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} DND Start"
        self._attr_unique_id = f"{mac_address}_dnd_start"
        self._attr_icon = "mdi:bell-sleep"


class GlanceClockDndEndNumber(GlanceClockDndHourNumber):
    """Hour the quiet period ends."""

    _setting_key = "dndTillHour"

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the DND end hour."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} DND End"
        self._attr_unique_id = f"{mac_address}_dnd_end"
        self._attr_icon = "mdi:bell-ring"


class GlanceClockAnimationSpeedNumber(GlanceClockEntity, NumberEntity, RestoreEntity):
    """Speed for the Run Animation button.

    The range spans negatives because the sweep uses the sign as its direction.
    The firmware animations have no direction and reject a negative value, which
    the run button reports rather than silently clamping.
    """

    _attr_native_min_value = -10
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the animation speed number."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Animation Speed"
        self._attr_unique_id = f"{mac_address}_animation_speed"
        self._attr_icon = "mdi:speedometer"

    @property
    def native_value(self) -> float | None:
        """Return the chosen speed."""
        return float(get_animation_state(self.hass, self._config_entry.entry_id)["speed"])

    @property
    def available(self) -> bool:
        """Always available; nothing is read from the clock."""
        return True

    async def async_set_native_value(self, value: float) -> None:
        """Remember the speed for the next run."""
        get_animation_state(self.hass, self._config_entry.entry_id)["speed"] = int(value)
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Restore the previous speed."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            try:
                get_animation_state(self.hass, self._config_entry.entry_id)["speed"] = int(
                    float(last.state)
                )
                self.async_write_ha_state()
            except (TypeError, ValueError):
                pass
