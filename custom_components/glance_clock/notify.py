import logging
import asyncio
from homeassistant.components.notify.legacy import BaseNotificationService
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, GLANCE_SERVICE_UUID, SETTINGS_CHARACTERISTIC_UUID
from bleak.backends.service import BleakGATTServiceCollection
from bleak_retry_connector import BleakClientWithServiceCache
from .glance_pb2 import Settings, ForecastScene  # type: ignore

_LOGGER = logging.getLogger(__name__)


class CharacteristicMissingError(Exception):
    """Raised when a required characteristic is missing."""
    pass


class GlanceClockNotificationService(BaseNotificationService):

    async def async_send_timer(self, countdown, intervals=None, final_text=None) -> bool:
        """Send a timer scene to the Glance Clock device."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send timer")
            return False

        try:
            from .glance_pb2 import Timer, TextData  # type: ignore
            import struct
            import time
            import re

            def text_with_icons_to_bytes(text: str) -> bytes:
                icon_regex = re.compile(r"\[icon:(\d+)\]")
                parts = []
                last_index = 0
                for match in icon_regex.finditer(text):
                    for c in text[last_index:match.start()]:
                        parts.append(ord(c) & 0x7F)
                    parts.append(int(match.group(1)))
                    last_index = match.end()
                for c in text[last_index:]:
                    parts.append(ord(c) & 0x7F)
                return bytes(parts)

            # Prepare intervals
            timer_intervals = []
            if intervals:
                for interval in intervals:
                    interval_text = interval.get('text', '')
                    interval_duration = interval.get('duration', 0)
                    interval_countdown = interval.get('countdown', 0)
                    text_data = TextData()
                    text_data.text = text_with_icons_to_bytes(interval_text)
                    timer_intervals.append({
                        'text': [text_data],
                        'duration': interval_duration,
                        'countdown': interval_countdown
                    })

            # Prepare final text
            final_texts = []
            if final_text:
                if isinstance(final_text, list):
                    for t in final_text:
                        text_data = TextData()
                        text_data.text = text_with_icons_to_bytes(t)
                        final_texts.append(text_data)
                else:
                    text_data = TextData()
                    text_data.text = text_with_icons_to_bytes(final_text)
                    final_texts.append(text_data)

            # Create Timer protobuf message
            timer_msg = Timer()
            timer_msg.countdown = int(countdown)
            for interval in timer_intervals:
                i = timer_msg.intervals.add()
                i.duration = int(interval['duration'])
                i.countdown = int(interval['countdown'])
                for t in interval['text']:
                    i.text.append(t)
            for t in final_texts:
                timer_msg.finalText.append(t)

            timer_bytes = timer_msg.SerializeToString()
            header = bytearray([3, 0, 0, 0])
            command = header + timer_bytes

            _LOGGER.info(f"Sending timer: countdown={countdown}, intervals={len(timer_intervals)}, final_texts={len(final_texts)}")
            _LOGGER.debug(f"Timer command: {command.hex()}")

            success = await self._connection_manager.send_command(bytes(command))
            if success:
                _LOGGER.info("Timer sent successfully")
                return True
            else:
                _LOGGER.error("Failed to send timer command")
                return False
        except Exception as e:
            _LOGGER.error(f"Error sending timer: {e}")
            return False
    """Notification service for the Glance Clock - focused on settings reading."""

    def __init__(self, config_data):
        self._config_data = config_data
        self._mac_address = config_data.get("mac_address")
        self._name = config_data.get("name")
        self._connection_manager = config_data.get("connection_manager")

        # Debug what we received
        _LOGGER.debug(f"Notification service init for {self._name}")
        _LOGGER.debug(
            f"Config data keys: {list(config_data.keys()) if config_data else 'None'}")
        _LOGGER.debug(f"Connection manager: {self._connection_manager}")
        _LOGGER.debug(
            f"Connection manager type: {type(self._connection_manager)}")

        if self._connection_manager:
            _LOGGER.debug(
                f"Connection manager attributes: {dir(self._connection_manager)}")
            _LOGGER.debug(
                f"Has is_connected: {hasattr(self._connection_manager, 'is_connected')}")
            _LOGGER.info(
                f"Has client: {hasattr(self._connection_manager, 'client')}")

    async def async_send_message(self, message="", **kwargs):
        """Send a notification message to the Glance Clock."""
        if not message:
            _LOGGER.warning("Cannot send empty notification message")
            return

        # Extract notification parameters from kwargs
        title = kwargs.get("title", "")
        data = kwargs.get("data", {})
        
        # Default notification settings
        animation = data.get("animation", 1)  # Default: Pulse
        sound = data.get("sound", 0)  # Default: None
        color = data.get("color", 12)  # Default: White
        priority = data.get("priority", 16)  # Default: Medium
        text_modifier = data.get("text_modifier", 0)  # Default: None
        
        # Combine title and message
        full_text = f"{title}: {message}" if title else message
        
        try:
            success = await self.async_send_notice(
                text=full_text,
                animation=animation,
                sound=sound,
                color=color,
                priority=priority,
                text_modifier=text_modifier
            )
            
            if success:
                _LOGGER.info(f"Notification sent successfully: {full_text}")
            else:
                _LOGGER.error(f"Failed to send notification: {full_text}")
                
        except Exception as e:
            _LOGGER.error(f"Error sending notification: {e}")

    async def async_send_notice(self, text: str, animation: int = 1, sound: int = 0, 
                              color: int = 12, priority: int = 16, text_modifier: int = 0) -> bool:
        """Send a notice to the Glance Clock device, supporting [icon:CODE] markers in text."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send notice")
            return False

        try:
            from .glance_pb2 import Notice, TextData  # type: ignore

            def text_with_icons_to_bytes(text: str) -> bytes:
                import re
                icon_regex = re.compile(r"\[icon:(\d+)\]")
                parts = []
                last_index = 0
                for match in icon_regex.finditer(text):
                    # Add ASCII bytes for text before the icon
                    for c in text[last_index:match.start()]:
                        parts.append(ord(c) & 0x7F)
                    # Add the icon byte
                    parts.append(int(match.group(1)))
                    last_index = match.end()
                # Add remaining text
                for c in text[last_index:]:
                    parts.append(ord(c) & 0x7F)
                return bytes(parts)

            # Create TextData for the notice
            text_data = TextData()
            text_data.text = text_with_icons_to_bytes(text)
            text_data.modificators = text_modifier

            # Create Notice protobuf message
            notice = Notice()
            notice.type = animation
            notice.sound = sound  
            notice.color = color
            # Notice expects a single TextData, not repeated
            notice.text.CopyFrom(text_data)

            # Serialize the notice
            notice_bytes = notice.SerializeToString()

            # Create command with header [2, priority, 0, 0] + notice data (matching web app)
            command = bytearray([2, priority, 0, 0])
            command.extend(notice_bytes)

            _LOGGER.info(f"Sending notice: '{text}' (anim:{animation}, sound:{sound}, color:{color}, priority:{priority})")
            _LOGGER.debug(f"Notice command: {command.hex()}")

            # Send the command
            success = await self._connection_manager.send_command(bytes(command))

            if success:
                _LOGGER.info("Notice sent successfully")
                return True
            else:
                _LOGGER.error("Failed to send notice command")
                return False

        except Exception as e:
            _LOGGER.error(f"Error sending notice: {e}")
            return False

    async def async_read_current_settings(self) -> dict | None:
        """Read current settings from the Glance Clock device - with caching."""
        # Check if we have cached settings first
        if self._connection_manager:
            cached = self._connection_manager.get_cached_settings()
            if cached:
                _LOGGER.debug("Using cached settings")
                return cached

        _LOGGER.debug(f"Reading settings from {self._name} ({self._mac_address})")

        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.debug("No active connection for settings reading")
            return None

        try:
            client: BleakClientWithServiceCache = self._connection_manager.client
            if not client or not client.is_connected:
                _LOGGER.debug("BLE client not available")
                return None

            # Use the exact same approach as connection manager ping - simple and direct
            _LOGGER.debug("Reading settings characteristic")

            try:
                service = client.services.get_service(GLANCE_SERVICE_UUID)
                if not service:
                    raise CharacteristicMissingError(
                        f"Service {GLANCE_SERVICE_UUID} not found")

                char = service.get_characteristic(SETTINGS_CHARACTERISTIC_UUID)
                if not char:
                    raise CharacteristicMissingError(
                        f"Characteristic {SETTINGS_CHARACTERISTIC_UUID} not found")
                _LOGGER.debug(f"Found service {service.obj}")
                _LOGGER.debug(f"Found settings characteristic: {char.obj}")

                _LOGGER.debug("Reading settings characteristic...")

                await client.connect()

                raw_data = await asyncio.wait_for(client.read_gatt_char(char), timeout=10)

                _LOGGER.debug(f"Read value: {raw_data}")

            except (CharacteristicMissingError, KeyError, Exception) as ex:
                _LOGGER.error(f"Characteristic exploration failed: {ex}")

            if len(raw_data) > 0:
                # Check if this is descriptor data starting with "Data" (0x44617461)
                if raw_data[:4] == b'Data':
                    _LOGGER.debug("Found descriptor data starting with 'Data'")
                    # The actual protobuf data comes after "Data" + 1 byte
                    # Based on the hex: 4461746100071003cc2e002014100010c12e0200
                    # "Data" = 44617461, then 00, then protobuf starts at 071003...
                    # Skip "Data" (4 bytes) + null byte (1 byte)
                    protobuf_data = raw_data[5:]
                else:
                    # Standard characteristic data - use web project logic
                    protobuf_data = raw_data[1:] if raw_data[0] == 5 else raw_data
            else:
                protobuf_data = raw_data

            _LOGGER.debug(f"Protobuf data for parsing: {protobuf_data.hex()}")

            if len(protobuf_data) == 0:
                _LOGGER.warning("No protobuf data after header processing")
                return None

            # Decode protobuf using the same approach as web project
            try:
                # Create Settings message to decode the response  
                from .glance_pb2 import Settings  # type: ignore
                settings = Settings()
                settings.ParseFromString(protobuf_data)
                _LOGGER.debug("Successfully parsed protobuf settings")
            except Exception as pb_error:
                _LOGGER.error(f"Protobuf parsing failed: {pb_error}")
                _LOGGER.debug("Raw data analysis:")
                _LOGGER.debug(f"  Full hex: {raw_data.hex()}")
                _LOGGER.debug(
                    f"  First 10 bytes: {raw_data[:10].hex() if len(raw_data) >= 10 else raw_data.hex()}")
                _LOGGER.debug(f"  Protobuf attempt: {protobuf_data.hex()}")
                return None

            # Convert to dictionary
            settings_dict = {
                "nightModeEnabled": settings.nightModeEnabled,
                "pointsAlwaysEnabled": settings.pointsAlwaysEnabled,
                "displayBrightness": settings.displayBrightness,
                "timeModeEnable": settings.timeModeEnable,
                "timeFormat12": settings.timeFormat12,
                "permanentDND": settings.permanentDND,
                "permanentMute": settings.permanentMute,
                "dateFormat": settings.dateFormat,
                "mgrUserActivityTimeout": settings.mgrUserActivityTimeout,
            }

            _LOGGER.debug("Successfully read settings from device")

            # Cache the settings
            if self._connection_manager:
                self._connection_manager.cache_settings(settings_dict)

            return settings_dict

        except Exception as e:
            _LOGGER.debug(f"Could not read settings from device: {e}")
            return None

    async def async_read_current_settings_safe(self) -> dict | None:
        """Safe wrapper for reading settings."""
        return await self.async_read_current_settings()

    async def async_update_data(self) -> bool:
        """Send update data command (command 35) to prepare device for settings changes."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send update data command")
            return False

        try:
            # Send command 35 - equivalent to updateData() in web app
            success = await self._connection_manager.send_command(bytes([35]))
            if success:
                _LOGGER.debug("Update data command (35) sent successfully")
            else:
                _LOGGER.warning("Failed to send update data command (35)")
            return success
        except Exception as e:
            _LOGGER.error(f"Error sending update data command: {e}")
            return False

    async def async_brightness_scene_start(self) -> bool:
        """Send brightness scene start command (command 61) for brightness changes."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send brightness scene start command")
            return False

        try:
            # Send command 61 - equivalent to brightnessSceneStart() in web app
            success = await self._connection_manager.send_command(bytes([61]))
            if success:
                _LOGGER.debug("Brightness scene start command (61) sent successfully")
            else:
                _LOGGER.warning("Failed to send brightness scene start command (61)")
            return success
        except Exception as e:
            _LOGGER.error(f"Error sending brightness scene start command: {e}")
            return False

    async def async_brightness_scene_stop(self) -> bool:
        """Send brightness scene stop command (command 60) to stop brightness scene."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send brightness scene stop command")
            return False

        try:
            # Send command 60 - equivalent to brightnessSceneStop() in web app
            success = await self._connection_manager.send_command(bytes([60]))
            if success:
                _LOGGER.debug("Brightness scene stop command (60) sent successfully")
            else:
                _LOGGER.warning("Failed to send brightness scene stop command (60)")
            return success
        except Exception as e:
            _LOGGER.error(f"Error sending brightness scene stop command: {e}")
            return False

    async def async_write_settings(self, settings_data: dict) -> bool:
        """Write settings to the Glance Clock device."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot write settings")
            return False

        try:
            # Send update data command first (like web app does)
            # Check if this is a brightness change to determine which command to send
            is_brightness_change = "displayBrightness" in settings_data
            
            if is_brightness_change:
                _LOGGER.info("Brightness change detected, sending brightness scene start command")
                await self.async_brightness_scene_start()
            else:
                _LOGGER.info("Sending update data command before settings write")
                await self.async_update_data()

            # First read current settings to preserve existing values
            current_settings = await self.async_read_current_settings()
            if not current_settings:
                # If we can't read current settings, use default values
                current_settings = {
                    "nightModeEnabled": True,
                    "pointsAlwaysEnabled": False,
                    "displayBrightness": 128,
                    "timeModeEnable": True,
                    "timeFormat12": False,
                    "permanentDND": False,
                    "permanentMute": False,
                    "dateFormat": 0,
                    "mgrUserActivityTimeout": 600,
                }
                _LOGGER.debug("Using default settings as base")

            # Update only the specified settings
            updated_settings = current_settings.copy()
            updated_settings.update(settings_data)

            # Create protobuf Settings message
            settings = Settings()
            
            # Map the dictionary to protobuf fields
            settings.nightModeEnabled = updated_settings.get("nightModeEnabled", True)
            settings.pointsAlwaysEnabled = updated_settings.get("pointsAlwaysEnabled", False)
            settings.displayBrightness = updated_settings.get("displayBrightness", 128)
            settings.timeModeEnable = updated_settings.get("timeModeEnable", True)
            settings.timeFormat12 = updated_settings.get("timeFormat12", False)
            settings.permanentDND = updated_settings.get("permanentDND", False)
            settings.permanentMute = updated_settings.get("permanentMute", False)
            settings.dateFormat = updated_settings.get("dateFormat", 0)
            settings.mgrUserActivityTimeout = updated_settings.get("mgrUserActivityTimeout", 600)

            # Serialize the settings
            settings_bytes = settings.SerializeToString()

            # Create command with header [5, 0, 0, 0] + settings data
            command = bytearray([5, 0, 0, 0])
            command.extend(settings_bytes)

            _LOGGER.info(f"Writing settings to device: {settings_data}")
            
            # Send the command
            success = await self._connection_manager.send_command(bytes(command))
            
            if success:
                _LOGGER.info("Settings written successfully")
                
                # If this was a brightness change, schedule brightness scene stop after 3 seconds
                # (like the web app does)
                if is_brightness_change:
                    _LOGGER.info("Scheduling brightness scene stop in 3 seconds")
                    asyncio.create_task(self._delayed_brightness_scene_stop())
                
                return True
            else:
                _LOGGER.error("Failed to send settings command")
                return False

        except Exception as e:
            _LOGGER.error(f"Error writing settings: {e}")
            return False

    async def _delayed_brightness_scene_stop(self) -> None:
        """Stop brightness scene after a 3-second delay (matches web app behavior)."""
        try:
            await asyncio.sleep(3.0)
            await self.async_brightness_scene_stop()
            _LOGGER.info("Brightness scene stopped after delay")
        except Exception as e:
            _LOGGER.error(f"Error in delayed brightness scene stop: {e}")

    async def async_send_forecast(
        self,
        max_temp: int,
        min_temp: int,
        max_color: int,
        min_color: int,
        values: bytes,
        start_timestamp: int,
        template: bytes | None = None
    ) -> bool:
        """Send weather forecast data to the Glance Clock."""
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send forecast")
            return False

        try:
            import time
            import struct
            
            _LOGGER.info("=== SENDING WEATHER FORECAST ===")
            _LOGGER.info(f"Temperature range: {min_temp}° to {max_temp}°")
            _LOGGER.info(f"Max color: 0x{max_color:06X} ({max_color})")
            _LOGGER.info(f"Min color: 0x{min_color:06X} ({min_color})")
            _LOGGER.info(f"Temperature values ({len(values)} bytes): {values.hex()}")
            
            # Default template matching web project: thermometer icon + current value + °C
            if template is None:
                # Template: [194, 143, 8, 194, 176, 67] = thermometer icon + value placeholder + °C
                default_template = bytes([194, 143, 8, 194, 176, 67])  # 67 = 'C'
                template = default_template
                _LOGGER.info(f"Using default template: {template.hex()}")
            else:
                _LOGGER.info(f"Using custom template ({len(template)} bytes): {template.hex()}")
            
            # Send update data command first (like we do for settings)
            _LOGGER.info("Sending update data command (35) before forecast...")
            update_success = await self.async_update_data()
            if update_success:
                _LOGGER.info("✓ Update data command sent successfully")
            else:
                _LOGGER.warning("⚠ Update data command failed, continuing anyway...")
            
            # Create ForecastScene message
            forecast_scene = ForecastScene()
            
            # Use the provided start timestamp (already calculated from forecast data)
            import datetime
            forecast_scene.timestamp = start_timestamp
            forecast_scene.max = max_temp
            forecast_scene.min = min_temp
            forecast_scene.maxColor = max_color
            forecast_scene.minColor = min_color
            forecast_scene.values = values
            forecast_scene.template = template
            
            _LOGGER.info(f"Created ForecastScene:")
            _LOGGER.info(f"  Forecast start timestamp: {start_timestamp}")
            try:
                # Use modern timezone-aware approach
                forecast_time = datetime.datetime.fromtimestamp(start_timestamp)
                _LOGGER.info(f"  Forecast start time: {forecast_time}")
            except Exception:
                # Fallback
                _LOGGER.info(f"  Forecast start time: {datetime.datetime.fromtimestamp(start_timestamp)}")
            _LOGGER.info(f"  Max/Min: {max_temp}°/{min_temp}°")
            _LOGGER.info(f"  Values: 24 temperatures encoded as Int16LE")

            # Serialize the forecast scene
            forecast_bytes = forecast_scene.SerializeToString()
            _LOGGER.info(f"Serialized forecast data: {len(forecast_bytes)} bytes")
            _LOGGER.debug(f"Protobuf data: {forecast_bytes.hex()}")

            # Create command with header matching web project: [7, priority, 24, 1] + forecast data
            # Priority: 16 (SCENE_PRIORITY_BAND_MEDIUM), 24 hours, slot 1
            command = bytearray([7, 16, 24, 1])
            command.extend(forecast_bytes)

            _LOGGER.info(f"Full command: {len(command)} bytes total")
            _LOGGER.info(f"Command header: [7, 16, 24, 1] (forecast scene, medium priority, 24h, slot 1)")
            _LOGGER.info(f"Command hex: {command.hex()}")
            
            # Send the command
            _LOGGER.info("Sending forecast command to device...")
            success = await self._connection_manager.send_command(bytes(command))
            
            if success:
                _LOGGER.info("✓ Weather forecast sent successfully!")
                return True
            else:
                _LOGGER.error("✗ Failed to send forecast command")
                return False

        except Exception as e:
            _LOGGER.error(f"✗ Error sending forecast: {e}")
            import traceback
            _LOGGER.error(f"Full traceback: {traceback.format_exc()}")
            return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> bool:
    """Set up the Glance Clock notification service."""
    config_data = hass.data[DOMAIN][entry.entry_id]

    # Create notification service
    notify_service = GlanceClockNotificationService(config_data)

    # Store the service for access by entities
    if DOMAIN + "_notify" not in hass.data:
        hass.data[DOMAIN + "_notify"] = {}
    hass.data[DOMAIN + "_notify"][entry.entry_id] = notify_service

    _LOGGER.info(
        f"Glance Clock notification service set up for {config_data.get('name')}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the notification service."""
    if DOMAIN + "_notify" in hass.data:
        hass.data[DOMAIN + "_notify"].pop(entry.entry_id, None)
    return True
