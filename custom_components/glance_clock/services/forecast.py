"""Weather forecast service for Glance Clock."""
import logging
import struct
import time
import datetime
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry

from ..const import DOMAIN
from ..utils.color_utils import parse_color_input, interpolate_color

_LOGGER = logging.getLogger(__name__)


async def handle_send_forecast(hass: HomeAssistant, entry: ConfigEntry, call: ServiceCall):
    """Handle sending weather forecast to the device."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry.entry_id)
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
    _LOGGER.debug(
        f"Weather entity attributes: {dict(weather_state.attributes)}")

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
        temps, actual_min_temp, actual_max_temp, forecast_min_temp, forecast_max_temp = \
            await _process_forecast_data(hass, forecast, weather_state)

        if not temps:
            _LOGGER.error("No temperature data in forecast")
            return

        # Get color settings
        max_color = parse_color_input(call.data.get("max_color"), 0xFF0000)
        min_color = parse_color_input(call.data.get("min_color"), 0x0000FF)
        user_min_value = call.data.get("min_value")
        user_max_value = call.data.get("max_value")

        # Calculate gradient colors
        gradient_min, gradient_max, gradient_min_color, gradient_max_color = \
            _calculate_gradient_colors(
                actual_min_temp, actual_max_temp,
                forecast_min_temp, forecast_max_temp,
                user_min_value, user_max_value,
                min_color, max_color
            )

        _LOGGER.info(
            f"Weather forecast processed: {actual_min_temp}°-{actual_max_temp}° over 24h")
        _LOGGER.debug(f"Temperature data summary:")
        _LOGGER.debug(
            f"  Actual 24h range: {actual_min_temp}° to {actual_max_temp}°")
        _LOGGER.debug(
            f"  Clock min/max: {forecast_min_temp}° to {forecast_max_temp}°")
        _LOGGER.debug(f"  Gradient range: {gradient_min}° to {gradient_max}°")
        _LOGGER.debug(
            f"  Gradient colors - Min: 0x{gradient_min_color:06X}, Max: 0x{gradient_max_color:06X}")
        _LOGGER.debug(f"24-hour temperatures: {temps}")

        # Convert to bytes
        values = bytearray()
        for temp in temps:
            values.extend(struct.pack('<h', temp))

        _LOGGER.debug(
            f"Final temperature array ({len(values)} bytes): {values.hex()}")

        # Calculate timestamp
        forecast_start_timestamp = _calculate_forecast_timestamp()

        # Send to device
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


async def _process_forecast_data(hass: HomeAssistant, forecast: list, weather_state) -> tuple:
    """Process forecast data and return temperature arrays."""
    now = datetime.datetime.now()

    # Get local timezone
    try:
        local_tz = datetime.datetime.now().astimezone().tzinfo
    except AttributeError:
        local_tz = datetime.timezone(
            datetime.timedelta(seconds=-time.timezone))

    current_aware = now.replace(tzinfo=local_tz)
    current_hour = current_aware.replace(minute=0, second=0, microsecond=0)

    # Find current hour index
    current_hour_index = 0
    first_forecast_time = None

    for i, hour in enumerate(forecast):
        if not isinstance(hour, dict):
            continue

        dt_str = hour.get('datetime')
        if dt_str:
            try:
                dt = _parse_datetime(dt_str)
                if dt is None:
                    continue

                if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
                    dt_local = dt.astimezone()
                else:
                    dt_local = dt.replace(tzinfo=local_tz)

                dt_local_hour = dt_local.replace(
                    minute=0, second=0, microsecond=0)

                if first_forecast_time is None:
                    first_forecast_time = dt_local
                    current_hour_index = i

                if dt_local_hour >= current_hour:
                    current_hour_index = i
                    first_forecast_time = dt_local
                    _LOGGER.debug(
                        f"Found matching hour: {dt_local} (index {i})")
                    break

            except Exception as e:
                _LOGGER.debug(f"Could not parse datetime {dt_str}: {e}")
                continue

    # Get 24 hours of forecast
    forecast_24h = forecast[current_hour_index:current_hour_index + 24]
    while len(forecast_24h) < 24 and len(forecast) > 0:
        forecast_24h.append(forecast[-1])

    # Extract temperatures
    forecast_temps = []
    forecast_max_temp = None
    forecast_min_temp = None

    for hour in forecast_24h[:23]:
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

    # Get current temperature
    current_temp = None
    if weather_state.state not in [None, "unavailable", "unknown"]:
        try:
            current_temp_attr = weather_state.attributes.get("temperature")
            if current_temp_attr is not None:
                current_temp = int(float(current_temp_attr))
                _LOGGER.debug(f"Current temperature: {current_temp}°")
        except (ValueError, TypeError):
            _LOGGER.warning(f"Could not parse current temperature")

    # Build final 24-hour array
    temps = []
    if current_temp is not None:
        temps.append(current_temp)
        if forecast_max_temp is None or current_temp > forecast_max_temp:
            forecast_max_temp = current_temp
        if forecast_min_temp is None or current_temp < forecast_min_temp:
            forecast_min_temp = current_temp
    else:
        temps.append(forecast_temps[0] if forecast_temps else 20)

    temps.extend(forecast_temps)

    while len(temps) < 24:
        temps.append(temps[-1] if temps else 20)
    temps = temps[:24]

    actual_min_temp = min(temps)
    actual_max_temp = max(temps)

    return temps, actual_min_temp, actual_max_temp, forecast_min_temp, forecast_max_temp


def _parse_datetime(dt_str):
    """Parse datetime string to datetime object."""
    if isinstance(dt_str, datetime.datetime):
        return dt_str

    if not isinstance(dt_str, str):
        return None

    if 'T' not in dt_str:
        return datetime.datetime.fromisoformat(dt_str)

    if dt_str.endswith('Z'):
        return datetime.datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
    elif '+' in dt_str or dt_str.count('-') > 2:
        return datetime.datetime.fromisoformat(dt_str)
    else:
        return datetime.datetime.fromisoformat(dt_str)


def _calculate_gradient_colors(actual_min_temp, actual_max_temp, forecast_min_temp,
                               forecast_max_temp, user_min_value, user_max_value,
                               min_color, max_color) -> tuple:
    """Calculate gradient colors based on temperature range."""
    if user_min_value is not None and user_max_value is not None:
        gradient_min = user_min_value
        gradient_max = user_max_value
        _LOGGER.debug(
            f"Using user-defined gradient range: {gradient_min}° to {gradient_max}°")
    else:
        gradient_min = forecast_min_temp or 0
        gradient_max = forecast_max_temp or 30
        _LOGGER.debug(
            f"Using forecast range: {gradient_min}° to {gradient_max}°")

    gradient_min_color = interpolate_color(
        actual_min_temp, gradient_min, gradient_max, min_color, max_color
    )
    gradient_max_color = interpolate_color(
        actual_max_temp, gradient_min, gradient_max, min_color, max_color
    )

    return gradient_min, gradient_max, gradient_min_color, gradient_max_color


def _calculate_forecast_timestamp() -> int:
    """Calculate forecast start timestamp in local time."""
    utc_timestamp = int(time.time())
    timezone_offset_seconds = time.timezone if time.daylight == 0 else time.altzone
    forecast_start_timestamp = utc_timestamp - timezone_offset_seconds

    _LOGGER.debug(f"Using current time as forecast start:")
    _LOGGER.debug(f"  UTC timestamp: {utc_timestamp}")
    _LOGGER.debug(f"  Timezone offset: {timezone_offset_seconds} seconds")
    _LOGGER.debug(f"  Local timestamp: {forecast_start_timestamp}")

    return forecast_start_timestamp
