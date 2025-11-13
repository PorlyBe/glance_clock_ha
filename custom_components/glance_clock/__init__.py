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

from .const import GLANCE_CHARACTERISTIC_UUID, DOMAIN
from .utils.color_utils import parse_color_input, interpolate_color

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
        self._connection_callbacks = []  # Add callback system
        self._cached_settings = None  # Cache settings to avoid multiple reads
        self._settings_read_time = None  # Track when settings were last read

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

    def get_cached_settings(self):
        """Get cached settings if available and fresh."""
        import time
        if self._cached_settings and self._settings_read_time:
            # Cache is valid for 60 seconds
            if time.time() - self._settings_read_time < 60:
                return self._cached_settings
        return None

    def cache_settings(self, settings):
        """Cache settings with timestamp."""
        import time
        self._cached_settings = settings
        self._settings_read_time = time.time()

    def clear_settings_cache(self):
        """Clear cached settings."""
        self._cached_settings = None
        self._settings_read_time = None

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
                self.hass, self.mac_address, connectable=True)

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

                # Notify all registered callbacks about successful connection
                await self._notify_connection_callbacks()
            else:
                raise Exception("Failed to establish connection")

        except Exception as e:
            self._reconnect_attempts += 1
            _LOGGER.error(
                f"Connection failed (attempt {self._reconnect_attempts}): {e}")

            if self._reconnect_attempts < self._max_reconnect_attempts:
                wait_time = 30 * self._reconnect_attempts
                await asyncio.sleep(wait_time)
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

    # Get data from config entry (support both old and new format)
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

    # Create simple Bluetooth coordinator for device detection
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

    # Device registry entry will be created by sensor entities after reading real device info
    # This ensures we don't use fallback data when real device info is available

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Start coordinator
    entry.async_on_unload(coordinator.async_start())

    # Register essential services for display settings
    async def handle_update_display_settings(call):
        """Handle display settings update requests."""
        entry_data = hass.data[DOMAIN][entry.entry_id]
        notify_service = hass.data.get(
            DOMAIN + "_notify", {}).get(entry.entry_id)
        connection_manager = entry_data.get("connection_manager")

        if notify_service:
            if connection_manager and not hasattr(notify_service, '_connection_manager'):
                notify_service._connection_manager = connection_manager

            success = await notify_service.async_write_settings(call.data)
            if success:
                _LOGGER.info("Display settings updated successfully")
            else:
                _LOGGER.error("Failed to update display settings")
        else:
            _LOGGER.error(
                "Notification service not found for display settings")

    async def handle_read_current_settings(call):
        """Handle reading current device settings."""
        entry_data = hass.data[DOMAIN][entry.entry_id]
        notify_service = hass.data.get(
            DOMAIN + "_notify", {}).get(entry.entry_id)
        connection_manager = entry_data.get("connection_manager")

        if notify_service:
            if connection_manager and not hasattr(notify_service, '_connection_manager'):
                notify_service._connection_manager = connection_manager

            settings = await notify_service.async_read_current_settings_safe()
            if settings:
                _LOGGER.debug("Current settings read successfully:")
                for key, value in settings.items():
                    _LOGGER.debug(f"  {key}: {value}")
            else:
                _LOGGER.error("Failed to read current settings")
        else:
            _LOGGER.error(
                "Notification service not found for reading settings")

    async def handle_refresh_entities(call):
        """Handle refreshing entity states."""
        entity_registry = hass.helpers.entity_registry.async_get(hass)
        entities = hass.helpers.entity_registry.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )

        for entity_entry in entities:
            entity_id = entity_entry.entity_id
            await hass.helpers.entity_component.async_update_entity(hass, entity_id)

    async def handle_send_notice(call):
        """Handle sending notification notices to the device."""
        from .const import ANIMATIONS, SOUNDS, COLORS, PRIORITIES, TEXT_MODIFIERS

        entry_data = hass.data[DOMAIN][entry.entry_id]
        notify_service = hass.data.get(
            DOMAIN + "_notify", {}).get(entry.entry_id)
        connection_manager = entry_data.get("connection_manager")

        if notify_service:
            if connection_manager and not hasattr(notify_service, '_connection_manager'):
                notify_service._connection_manager = connection_manager

            # Extract parameters
            text = call.data.get("text", "")
            animation_name = call.data.get("animation", "pulse")
            sound_name = call.data.get("sound", "none")
            color_name = call.data.get("color", "white")
            priority_name = call.data.get("priority", "medium")
            modifier_name = call.data.get("text_modifier", "none")

            # Convert names to numeric values
            animation = ANIMATIONS.get(animation_name, 1)  # Default to pulse
            sound = SOUNDS.get(sound_name, 0)  # Default to none
            color = COLORS.get(color_name, 12)  # Default to white
            priority = PRIORITIES.get(priority_name, 16)  # Default to medium
            text_modifier = TEXT_MODIFIERS.get(
                modifier_name, 0)  # Default to none

            success = await notify_service.async_send_notice(
                text=text,
                animation=animation,
                sound=sound,
                color=color,
                priority=priority,
                text_modifier=text_modifier
            )

            if success:
                _LOGGER.info(f"Notice sent successfully: {text}")
            else:
                _LOGGER.error(f"Failed to send notice: {text}")
        else:
            _LOGGER.error("Notification service not found for sending notice")

    async def handle_send_forecast(call):
        """Handle sending weather forecast to the device."""
        entry_data = hass.data[DOMAIN][entry.entry_id]
        notify_service = hass.data.get(
            DOMAIN + "_notify", {}).get(entry.entry_id)
        connection_manager = entry_data.get("connection_manager")

        _LOGGER.debug("=== WEATHER FORECAST SERVICE CALLED ===")
        _LOGGER.debug(f"Call data: {call.data}")

        if notify_service:
            if connection_manager and not hasattr(notify_service, '_connection_manager'):
                notify_service._connection_manager = connection_manager

            # Get weather entity
            weather_entity = call.data.get("weather_entity")
            if not weather_entity:
                _LOGGER.error("Weather entity is required for forecast")
                return

            _LOGGER.debug(f"Using weather entity: {weather_entity}")

            # Get the weather entity state
            weather_state = hass.states.get(weather_entity)
            if not weather_state:
                _LOGGER.error(f"Weather entity {weather_entity} not found")
                return

            _LOGGER.debug(f"Weather entity state: {weather_state.state}")
            _LOGGER.debug(
                f"Weather entity attributes: {dict(weather_state.attributes)}")

            # Get forecast from weather entity
            try:
                _LOGGER.debug("Calling weather.get_forecasts service...")
                forecast_data = await hass.services.async_call(
                    "weather", "get_forecasts",
                    # Changed to hourly
                    {"entity_id": weather_entity, "type": "hourly"},
                    blocking=True,
                    return_response=True
                )

                _LOGGER.debug(f"Raw forecast response: {forecast_data}")

                # Handle the response format
                if not isinstance(forecast_data, dict):
                    _LOGGER.error("Invalid forecast data format")
                    return

                entity_forecast = forecast_data.get(weather_entity)
                _LOGGER.debug(f"Entity forecast data: {entity_forecast}")

                if not isinstance(entity_forecast, dict):
                    _LOGGER.error("Invalid entity forecast data format")
                    return

                forecast = entity_forecast.get("forecast", [])
                if not isinstance(forecast, list):
                    _LOGGER.error("Invalid forecast list format")
                    return

                if not forecast:
                    _LOGGER.error("No forecast data available")
                    return

                _LOGGER.debug(f"Found {len(forecast)} hourly forecast entries")

                # Find the current time or closest future time to align forecast
                import datetime
                now = datetime.datetime.now()
                now_utc = datetime.datetime.utcnow()

                _LOGGER.debug(f"Current local time: {now}")
                _LOGGER.debug(f"Current UTC time: {now_utc}")

                # Find the forecast entry that starts closest to current time
                current_hour_index = 0
                first_forecast_time = None

                # Ensure current time is timezone-aware for proper comparison
                try:
                    # Get local timezone
                    local_tz = datetime.datetime.now().astimezone().tzinfo
                except AttributeError:
                    # Fallback for older Python versions
                    import time
                    local_tz = datetime.timezone(
                        datetime.timedelta(seconds=-time.timezone))

                current_aware = now.replace(tzinfo=local_tz)
                current_hour = current_aware.replace(
                    minute=0, second=0, microsecond=0)
                _LOGGER.debug(
                    f"Looking for forecast at or after: {current_hour}")

                for i, hour in enumerate(forecast):
                    if not isinstance(hour, dict):
                        continue

                    dt_str = hour.get('datetime')
                    if dt_str:
                        try:
                            # Parse the datetime string - typically ISO format
                            dt = None
                            if isinstance(dt_str, str):
                                # Handle ISO format with timezone
                                if 'T' in dt_str:
                                    if dt_str.endswith('Z'):
                                        dt = datetime.datetime.fromisoformat(
                                            dt_str.replace('Z', '+00:00'))
                                    elif '+' in dt_str or dt_str.count('-') > 2:
                                        dt = datetime.datetime.fromisoformat(
                                            dt_str)
                                    else:
                                        dt = datetime.datetime.fromisoformat(
                                            dt_str)
                                else:
                                    dt = datetime.datetime.fromisoformat(
                                        dt_str)
                            elif isinstance(dt_str, datetime.datetime):
                                dt = dt_str

                            if dt is None:
                                continue

                            # Always convert to local timezone for comparison
                            if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                                dt_local = dt.astimezone()
                            else:
                                # If naive, assume it's already in local time
                                dt_local = dt.replace(tzinfo=local_tz)

                            dt_local_hour = dt_local.replace(
                                minute=0, second=0, microsecond=0)

                            if first_forecast_time is None:
                                first_forecast_time = dt_local
                                current_hour_index = i
                                _LOGGER.debug(
                                    f"First forecast entry: {dt_local} (index {i})")

                            # Check if this hour matches current or future hour
                            if dt_local_hour >= current_hour:
                                current_hour_index = i
                                first_forecast_time = dt_local
                                _LOGGER.debug(
                                    f"Found matching hour: {dt_local} (index {i}) - local hour {dt_local_hour} >= current hour {current_hour}")
                                break

                        except Exception as e:
                            _LOGGER.debug(
                                f"Could not parse datetime {dt_str}: {e}")
                            continue

                # Take 24 hours starting from the selected hour
                forecast_24h = forecast[current_hour_index:current_hour_index + 24]

                # If we don't have enough future hours, pad with the last available data
                while len(forecast_24h) < 24 and len(forecast) > 0:
                    # Repeat last forecast entry
                    forecast_24h.append(forecast[-1])

                _LOGGER.debug(
                    f"Using forecast starting from index {current_hour_index}")
                _LOGGER.debug(f"First forecast time: {first_forecast_time}")
                _LOGGER.debug(f"Selected {len(forecast_24h)} hourly entries")

                for i, hour in enumerate(forecast_24h):
                    if isinstance(hour, dict):
                        _LOGGER.debug(
                            f"Hour {i+1}: {hour.get('datetime', 'unknown')} - Temp: {hour.get('temperature')}°")

                # Get current temperature and colors from call data
                max_color = parse_color_input(call.data.get(
                    "max_color"), 0xFF0000)  # Default red
                min_color = parse_color_input(call.data.get(
                    "min_color"), 0x0000FF)  # Default blue

                # Get min/max value ranges for gradient (optional)
                user_min_value = call.data.get("min_value")
                user_max_value = call.data.get("max_value")

                _LOGGER.debug(
                    f"Color settings - Max: 0x{max_color:06X}, Min: 0x{min_color:06X}")
                if user_min_value is not None:
                    _LOGGER.debug(f"User-defined min value: {user_min_value}°")
                if user_max_value is not None:
                    _LOGGER.debug(f"User-defined max value: {user_max_value}°")

                # Get current temperature from weather entity
                current_temp = None
                if weather_state.state not in [None, "unavailable", "unknown"]:
                    try:
                        current_temp_attr = weather_state.attributes.get(
                            "temperature")
                        if current_temp_attr is not None:
                            current_temp = int(float(current_temp_attr))
                            _LOGGER.debug(
                                f"Current temperature: {current_temp}°")
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            f"Could not parse current temperature: {weather_state.attributes.get('temperature')}")

                # Extract forecast temperatures (we'll use 23 values, plus current as first)
                forecast_temps = []
                forecast_max_temp = None
                forecast_min_temp = None

                # Take 23 forecast values (since we'll add current temp as first)
                forecast_to_use = forecast_24h[:23] if len(
                    forecast_24h) >= 23 else forecast_24h

                for hour in forecast_to_use:
                    if not isinstance(hour, dict):
                        continue

                    temp = hour.get("temperature")

                    if temp is not None and isinstance(temp, (int, float, str)):
                        try:
                            temp_int = int(float(temp))
                            forecast_temps.append(temp_int)

                            if forecast_max_temp is None or temp_int > forecast_max_temp:
                                forecast_max_temp = temp_int
                            if forecast_min_temp is None or temp_int < forecast_min_temp:
                                forecast_min_temp = temp_int
                        except (ValueError, TypeError):
                            forecast_temps.append(20)  # Default temperature
                    else:
                        forecast_temps.append(20)  # Default temperature

                # Build final 24-hour temperature array: current + 23 forecast
                temps = []

                # First value: current temperature
                if current_temp is not None:
                    temps.append(current_temp)
                    _LOGGER.debug(
                        f"Using current temperature as first value: {current_temp}°")

                    # Include current temp in min/max calculation
                    if forecast_max_temp is None or current_temp > forecast_max_temp:
                        forecast_max_temp = current_temp
                    if forecast_min_temp is None or current_temp < forecast_min_temp:
                        forecast_min_temp = current_temp
                else:
                    # If no current temp available, use first forecast or default
                    if forecast_temps:
                        temps.append(forecast_temps[0])
                        _LOGGER.warning(
                            "No current temperature available, using first forecast value")
                    else:
                        temps.append(20)
                        _LOGGER.warning(
                            "No current or forecast temperature available, using default 20°")

                # Add forecast temperatures (up to 23 more)
                temps.extend(forecast_temps)

                # Pad or truncate to exactly 24 values
                while len(temps) < 24:
                    # Repeat last temp or use default
                    temps.append(temps[-1] if temps else 20)
                temps = temps[:24]  # Ensure exactly 24 values

                # Determine the range for color gradient calculation
                if user_min_value is not None and user_max_value is not None:
                    # Use user-defined range for gradient color calculation
                    gradient_min = user_min_value
                    gradient_max = user_max_value
                    _LOGGER.debug(
                        f"Using user-defined gradient range for colors: {gradient_min}° to {gradient_max}°")
                else:
                    # Use actual forecast range for gradient calculation
                    gradient_min = forecast_min_temp or 0
                    gradient_max = forecast_max_temp or 30
                    _LOGGER.debug(
                        f"Using actual forecast range for colors: {gradient_min}° to {gradient_max}°")

                # Actual temperature range from our 24-hour data (current + 23 forecast)
                actual_min_temp = min(temps)
                actual_max_temp = max(temps)

                # What gets sent to the clock: actual forecast min/max (for display/scaling)
                clock_min_temp = forecast_min_temp if forecast_min_temp is not None else actual_min_temp
                clock_max_temp = forecast_max_temp if forecast_max_temp is not None else actual_max_temp

                # Interpolate colors based on the gradient range (user-defined or forecast range)
                gradient_min_color = interpolate_color(
                    actual_min_temp, gradient_min, gradient_max, min_color, max_color)
                gradient_max_color = interpolate_color(
                    actual_max_temp, gradient_min, gradient_max, min_color, max_color)

                _LOGGER.info(
                    f"Weather forecast processed: {actual_min_temp}°-{actual_max_temp}° over 24h")
                _LOGGER.debug(f"Temperature data summary:")
                _LOGGER.debug(
                    f"  Actual 24h range: {actual_min_temp}° to {actual_max_temp}° (current + 23 forecast)")
                _LOGGER.debug(
                    f"  Clock min/max: {clock_min_temp}° to {clock_max_temp}° (sent to device)")
                _LOGGER.debug(
                    f"  Gradient range: {gradient_min}° to {gradient_max}° (for color calculation)")
                _LOGGER.debug(
                    f"  Gradient colors - Min: 0x{gradient_min_color:06X}, Max: 0x{gradient_max_color:06X}")
                _LOGGER.debug(f"24-hour temperatures: {temps}")

                if not temps:
                    _LOGGER.error("No temperature data in forecast")
                    return

                # Convert to Int16LE bytes (24 temperatures * 2 bytes each = 48 bytes)
                import struct
                values = bytearray()
                for temp in temps:
                    # Pack as little-endian signed 16-bit integer
                    values.extend(struct.pack('<h', temp))

                _LOGGER.debug(
                    f"Final temperature array ({len(values)} bytes): {values.hex()}")

                # Calculate forecast start timestamp (convert UTC to local time for device)
                import time
                import datetime
                utc_timestamp = int(time.time())
                timezone_offset_seconds = time.timezone if time.daylight == 0 else time.altzone
                forecast_start_timestamp = utc_timestamp - timezone_offset_seconds

                # For logging, also show what the original forecast time was
                if first_forecast_time:
                    original_forecast_timestamp = int(
                        first_forecast_time.timestamp())
                    _LOGGER.debug(
                        f"Original forecast time: {first_forecast_time} (timestamp: {original_forecast_timestamp})")

                _LOGGER.debug(
                    f"Using current time as forecast start (converted to local timezone):")
                _LOGGER.debug(f"  UTC timestamp: {utc_timestamp}")
                _LOGGER.debug(
                    f"  Timezone offset: {timezone_offset_seconds} seconds")
                _LOGGER.debug(f"  Local timestamp: {forecast_start_timestamp}")
                _LOGGER.debug(
                    f"  Local time: {datetime.datetime.fromtimestamp(utc_timestamp)}")
                try:
                    # Use modern timezone-aware approach to avoid deprecation warning
                    utc_time = datetime.datetime.fromtimestamp(
                        utc_timestamp, datetime.timezone.utc)
                    _LOGGER.debug(f"  UTC time: {utc_time}")
                except AttributeError:
                    # Fallback for older Python versions
                    _LOGGER.debug(
                        f"  UTC time: {datetime.datetime.utcfromtimestamp(forecast_start_timestamp)}")

                success = await notify_service.async_send_forecast(
                    max_temp=clock_max_temp or 30,
                    min_temp=clock_min_temp or 0,
                    max_color=gradient_max_color,
                    min_color=gradient_min_color,
                    values=bytes(values),
                    start_timestamp=forecast_start_timestamp,
                    # Let notify service handle default template
                    template=call.data.get("template", None)
                )

                if success:
                    _LOGGER.info(
                        "✓ Weather forecast service completed successfully")
                else:
                    _LOGGER.error("✗ Weather forecast service failed")

            except Exception as e:
                _LOGGER.error(f"✗ Error getting forecast data: {e}")
                import traceback
                _LOGGER.error(f"Full traceback: {traceback.format_exc()}")
        else:
            _LOGGER.error(
                "Notification service not found for sending forecast")

    async def handle_send_timer(call):
        """Handle sending a timer scene to the device."""
        entry_data = hass.data[DOMAIN][entry.entry_id]
        notify_service = hass.data.get(
            DOMAIN + "_notify", {}).get(entry.entry_id)
        connection_manager = entry_data.get("connection_manager")

        if notify_service:
            if connection_manager and not hasattr(notify_service, '_connection_manager'):
                notify_service._connection_manager = connection_manager

            countdown = call.data.get("countdown")
            intervals = call.data.get("intervals", [])
            final_text = call.data.get("final_text", "")

            success = await notify_service.async_send_timer(
                countdown=countdown,
                intervals=intervals,
                final_text=final_text
            )
            if success:
                _LOGGER.info(f"Timer sent successfully: {countdown}s")
            else:
                _LOGGER.error(f"Failed to send timer: {countdown}s")
        else:
            _LOGGER.error("Notification service not found for sending timer")

    # Register services
    hass.services.async_register(
        DOMAIN, "update_display_settings", handle_update_display_settings)
    hass.services.async_register(
        DOMAIN, "read_current_settings", handle_read_current_settings)
    hass.services.async_register(
        DOMAIN, "refresh_entities", handle_refresh_entities)
    hass.services.async_register(DOMAIN, "send_notice", handle_send_notice)
    hass.services.async_register(DOMAIN, "send_forecast", handle_send_forecast)
    hass.services.async_register(DOMAIN, "send_timer", handle_send_timer)

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
