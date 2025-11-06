"""Service handlers for Glance Clock integration."""
import logging
import datetime
import struct
import time

from homeassistant.core import HomeAssistant, ServiceCall

from .const import ANIMATIONS, SOUNDS, COLORS, PRIORITIES, TEXT_MODIFIERS
from .utils.colors import parse_color_input, interpolate_color

_LOGGER = logging.getLogger(__name__)

DOMAIN = "glance_clock"


async def handle_update_display_settings(hass: HomeAssistant, entry_id: str, call: ServiceCall):
    """Handle display settings update requests."""
    entry_data = hass.data[DOMAIN][entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry_id)
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
        _LOGGER.error("Notification service not found for display settings")


async def handle_read_current_settings(hass: HomeAssistant, entry_id: str, call: ServiceCall):
    """Handle reading current device settings."""
    entry_data = hass.data[DOMAIN][entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry_id)
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
        _LOGGER.error("Notification service not found for reading settings")


async def handle_refresh_entities(hass: HomeAssistant, entry_id: str, call: ServiceCall):
    """Handle refreshing entity states."""
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    entities = hass.helpers.entity_registry.async_entries_for_config_entry(
        entity_registry, entry_id
    )
    
    for entity_entry in entities:
        entity_id = entity_entry.entity_id
        await hass.helpers.entity_component.async_update_entity(hass, entity_id)


async def handle_send_notice(hass: HomeAssistant, entry_id: str, call: ServiceCall):
    """Handle sending notification notices to the device."""
    entry_data = hass.data[DOMAIN][entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry_id)
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
        animation = ANIMATIONS.get(animation_name, 1)
        sound = SOUNDS.get(sound_name, 0)
        color = COLORS.get(color_name, 12)
        priority = PRIORITIES.get(priority_name, 16)
        text_modifier = TEXT_MODIFIERS.get(modifier_name, 0)

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


async def handle_send_forecast(hass: HomeAssistant, entry_id: str, call: ServiceCall):
    """Handle sending weather forecast to the device."""
    entry_data = hass.data[DOMAIN][entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry_id)
    connection_manager = entry_data.get("connection_manager")

    _LOGGER.debug("=== WEATHER FORECAST SERVICE CALLED ===")
    _LOGGER.debug(f"Call data: {call.data}")

    if not notify_service:
        _LOGGER.error("Notification service not found for sending forecast")
        return

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
    _LOGGER.debug(f"Weather entity attributes: {dict(weather_state.attributes)}")

    # Get forecast from weather entity
    try:
        _LOGGER.debug("Calling weather.get_forecasts service...")
        forecast_data = await hass.services.async_call(
            "weather", "get_forecasts",
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
        
        # Process forecast data
        temps, actual_min_temp, actual_max_temp, forecast_min_temp, forecast_max_temp = (
            _process_forecast_data(hass, forecast, weather_state)
        )
        
        if not temps:
            _LOGGER.error("No temperature data in forecast")
            return

        # Get color settings
        max_color = parse_color_input(call.data.get("max_color"), 0xFF0000)
        min_color = parse_color_input(call.data.get("min_color"), 0x0000FF)
        user_min_value = call.data.get("min_value")
        user_max_value = call.data.get("max_value")
        
        # Determine gradient range
        if user_min_value is not None and user_max_value is not None:
            gradient_min = user_min_value
            gradient_max = user_max_value
            _LOGGER.debug(f"Using user-defined gradient range: {gradient_min}° to {gradient_max}°")
        else:
            gradient_min = forecast_min_temp or 0
            gradient_max = forecast_max_temp or 30
            _LOGGER.debug(f"Using actual forecast range: {gradient_min}° to {gradient_max}°")

        # Calculate gradient colors
        gradient_min_color = interpolate_color(actual_min_temp, gradient_min, gradient_max, min_color, max_color)
        gradient_max_color = interpolate_color(actual_max_temp, gradient_min, gradient_max, min_color, max_color)
        
        _LOGGER.info(f"Weather forecast processed: {actual_min_temp}°-{actual_max_temp}° over 24h")
        _LOGGER.debug(f"Gradient colors - Min: 0x{gradient_min_color:06X}, Max: 0x{gradient_max_color:06X}")

        # Convert to bytes
        values = bytearray()
        for temp in temps:
            values.extend(struct.pack('<h', temp))

        _LOGGER.debug(f"Final temperature array ({len(values)} bytes): {values.hex()}")

        # Calculate forecast start timestamp
        utc_timestamp = int(time.time())
        timezone_offset_seconds = time.timezone if time.daylight == 0 else time.altzone
        forecast_start_timestamp = utc_timestamp - timezone_offset_seconds
        
        _LOGGER.debug(f"Using current time as forecast start: {datetime.datetime.fromtimestamp(utc_timestamp)}")

        success = await notify_service.async_send_forecast(
            max_temp=forecast_max_temp or 30,
            min_temp=forecast_min_temp or 0,
            max_color=gradient_max_color,
            min_color=gradient_min_color,
            values=bytes(values),
            start_timestamp=forecast_start_timestamp,
            template=call.data.get("template", None)
        )
        
        if success:
            _LOGGER.info("✓ Weather forecast service completed successfully")
        else:
            _LOGGER.error("✗ Weather forecast service failed")
            
    except Exception as e:
        _LOGGER.error(f"✗ Error getting forecast data: {e}")
        import traceback
        _LOGGER.error(f"Full traceback: {traceback.format_exc()}")


def _process_forecast_data(hass: HomeAssistant, forecast: list, weather_state):
    """Process forecast data and return temperatures."""
    # Get current temperature
    current_temp = None
    if weather_state.state not in [None, "unavailable", "unknown"]:
        try:
            current_temp_attr = weather_state.attributes.get("temperature")
            if current_temp_attr is not None:
                current_temp = int(float(current_temp_attr))
                _LOGGER.debug(f"Current temperature: {current_temp}°")
        except (ValueError, TypeError):
            _LOGGER.warning(f"Could not parse current temperature: {weather_state.attributes.get('temperature')}")

    # Find current hour index
    now = datetime.datetime.now()
    local_tz = now.astimezone().tzinfo
    current_aware = now.replace(tzinfo=local_tz)
    current_hour = current_aware.replace(minute=0, second=0, microsecond=0)
    
    current_hour_index = 0
    for i, hour in enumerate(forecast):
        if not isinstance(hour, dict):
            continue
            
        dt_str = hour.get('datetime')
        if dt_str:
            try:
                dt = _parse_datetime(dt_str, local_tz)
                if dt is None:
                    continue
                
                dt_local_hour = dt.replace(minute=0, second=0, microsecond=0)
                
                if dt_local_hour >= current_hour:
                    current_hour_index = i
                    _LOGGER.debug(f"Found matching hour at index {i}: {dt}")
                    break
            except Exception as e:
                _LOGGER.debug(f"Could not parse datetime {dt_str}: {e}")
                continue
    
    # Take 23 forecast values (current temp will be first)
    forecast_24h = forecast[current_hour_index:current_hour_index + 23]
    
    # Extract temperatures
    forecast_temps = []
    forecast_max_temp = None
    forecast_min_temp = None
    
    for hour in forecast_24h:
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
                forecast_temps.append(20)
        else:
            forecast_temps.append(20)

    # Build final 24-hour array: current + 23 forecast
    temps = []
    
    if current_temp is not None:
        temps.append(current_temp)
        _LOGGER.debug(f"Using current temperature as first value: {current_temp}°")
        
        if forecast_max_temp is None or current_temp > forecast_max_temp:
            forecast_max_temp = current_temp
        if forecast_min_temp is None or current_temp < forecast_min_temp:
            forecast_min_temp = current_temp
    else:
        temps.append(forecast_temps[0] if forecast_temps else 20)
        _LOGGER.warning("No current temperature available, using first forecast value")
    
    temps.extend(forecast_temps)

    # Pad or truncate to exactly 24 values
    while len(temps) < 24:
        temps.append(temps[-1] if temps else 20)
    temps = temps[:24]

    actual_min_temp = min(temps)
    actual_max_temp = max(temps)
    
    return temps, actual_min_temp, actual_max_temp, forecast_min_temp, forecast_max_temp


def _parse_datetime(dt_str, local_tz):
    """Parse datetime string to datetime object."""
    if isinstance(dt_str, datetime.datetime):
        dt = dt_str
    elif isinstance(dt_str, str):
        if 'T' in dt_str:
            if dt_str.endswith('Z'):
                dt = datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
            else:
                dt = datetime.datetime.fromisoformat(dt_str)
        else:
            dt = datetime.datetime.fromisoformat(dt_str)
    else:
        return None
    
    # Convert to local timezone
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        return dt.astimezone()
    else:
        return dt.replace(tzinfo=local_tz)
