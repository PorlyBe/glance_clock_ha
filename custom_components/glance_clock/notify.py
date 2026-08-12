import logging
import asyncio
from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.components.notify.legacy import BaseNotificationService
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ServiceValidationError
from .const import (DND_FIELD_NAMES, DOMAIN, GLANCE_SERVICE_UUID, RAW_SETTINGS_KEY,
                    SETTINGS_CHARACTERISTIC_UUID, SETTINGS_FIELD_NAMES)
from bleak_retry_connector import BleakClientWithServiceCache
from .glance_pb2 import Settings, ForecastScene  # type: ignore

_LOGGER = logging.getLogger(__name__)


#: The matrix font is ASCII only. Masking a character to 7 bits turns the ones
#: people actually type into different letters -- 'a' becomes 'e', so "Hej da"
#: arrives as "Hej de". Mapping them to their closest ASCII form is wrong too,
#: but it is legible and predictable.
TRANSLITERATION = {
    "å": "a", "ä": "a", "ö": "o",
    "Å": "A", "Ä": "A", "Ö": "O",
    "é": "e", "è": "e", "ê": "e", "É": "E",
    "ü": "u", "Ü": "U", "ø": "o", "Ø": "O",
    "æ": "ae", "Æ": "AE", "ß": "ss",
    "–": "-", "—": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...",
}

#: Charcode 154 is the font's own "missing character" glyph.
MISSING_GLYPH = 154


def _encode_char(char: str) -> list:
    """Turn one character into display bytes.

    Anything that cannot be represented becomes the font's missing-character
    glyph, so a dropped letter is visible rather than silently changed.
    """
    out = []
    for replacement in TRANSLITERATION.get(char, char):
        code = ord(replacement)
        out.append(code if code < 128 else MISSING_GLYPH)
    return out


def text_with_icons_to_bytes(text: str) -> bytes:
    """Encode display text, expanding [icon:CODE] markers."""
    import re

    parts = []
    last_index = 0
    for match in re.finditer(r"\[icon:(\d+)\]", text):
        for char in text[last_index:match.start()]:
            parts.extend(_encode_char(char))
        parts.append(int(match.group(1)) & 0xFF)
        last_index = match.end()
    for char in text[last_index:]:
        parts.extend(_encode_char(char))
    return bytes(parts)


def _resolve_sound(value) -> int:
    """Accept a sound name from SOUNDS or a raw index."""
    from .const import SOUNDS
    from .utils.enums import lookup_enum

    return lookup_enum(SOUNDS, value, "sound")



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
        """Send a notification message to the Glance Clock.

        UNREACHABLE as things stand, and worth knowing before spending time on
        it. This class is a legacy BaseNotificationService, but nothing ever
        registers it as one: the platform's async_setup_entry builds the object,
        stores it in hass.data for the other services to use, and adds no
        entities. So `notify.glance_clock` does not exist and this method has no
        caller. Confirmed against a running Home Assistant 2026-08-12 -- the
        notify domain lists every mobile app and no clock.

        The class is really the integration's command layer wearing a notify
        platform as a setup hook, which is also why Platform.NOTIFY cannot
        simply be dropped: every other service reaches the clock through this
        object.

        Kept rather than deleted because it is correct code that a real notify
        entity could use. Use glance_clock.send_notice instead.
        """
        if not message:
            _LOGGER.warning("Cannot send empty notification message")
            return

        # Extract notification parameters from kwargs
        title = kwargs.get("title", "")
        data = kwargs.get("data", {})

        # The documented way to call this platform is with names -- animation:
        # "pulse", sound: "bells". Those went straight through to protobuf
        # integer fields, which raised and left the notification unsent, so the
        # example in the README could not have worked. Resolve them here, the
        # same way send_notice does; raw indices still pass through.
        from .services.notice import resolve_notice

        try:
            notice = resolve_notice(data)
        except (ValueError, TypeError) as err:
            _LOGGER.error("Cannot send notification: %s", err)
            return

        # Combine title and message
        full_text = f"{title}: {message}" if title else message

        try:
            success = await self.async_send_notice(text=full_text, **notice)

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

            settings_dict = self._settings_to_dict(settings, protobuf_data)

            _LOGGER.debug("Successfully read settings from device")

            # Cache the settings
            if self._connection_manager:
                self._connection_manager.cache_settings(settings_dict)

            return settings_dict

        except Exception as e:
            _LOGGER.debug(f"Could not read settings from device: {e}")
            return None

    #: Writing to a slot that is still playing works: the new scene replaces the
    #: old one and shows at once. Verified on hardware 2026-08-12 by sending two
    #: raw CustomScene frames to the same slot with nothing in between -- red,
    #: then lime -- and watching the ring turn lime immediately. The clearing
    #: that used to happen before every write was added in 1.14.0 on a theory
    #: that had already been disproven, and it is what made a scene take fifteen
    #: seconds to appear.

    async def _refresh_scene_playback(self) -> None:
        """Make a scene that has just been written take effect now.

        Without this the clock picks the new scene up on its own cycle, up to
        about fifteen seconds later. That delay was taken for firmware and
        written into the documentation as a law -- scenes are for state,
        notices are for events -- when it is really just the scene engine
        waiting for its next pass.

        Command 31 starts scene playback, and on hardware 2026-08-12 it brought
        the new scene up immediately with nothing visible to give it away.
        Command 35 does it too but draws the "fetching from the cloud"
        indicator, which is a strange thing to show for a cloud that shut down
        years ago, and 30 followed by 31 blinks the digital clockface -- which
        a progress ring updating every minute would do every minute.

        Best effort: the scene is already written and will appear on the cycle
        regardless, so a refusal here costs latency, not the update.
        """
        try:
            await self._connection_manager.send_command(bytes([31, 0, 0, 0]))
        except Exception as err:  # noqa: BLE001 -- bleak raises broadly
            _LOGGER.debug("Could not refresh scene playback: %s", err)

    async def async_send_custom_scene(
        self,
        segments: list[int],
        mode: int = 8,
        slot: int = 0,
        life_time: int = 50,
    ) -> bool:
        """Light areas of the four LED rings with a CustomScene fill.

        `mode` picks how the scene shares the display: 0 hides the digital
        clockface, 8 shows the scene on the watchface alongside it, 24 puts the
        scene into the rotation so it alternates with the clockface.

        Times are in frames at 50 FPS. A fill stays on screen after its lifetime
        ends, so a short lifetime is not a short display.
        """
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send custom scene")
            return False

        try:
            from .glance_pb2 import CustomScene  # type: ignore
            from .utils.led_utils import METHOD_FILL

            scene = CustomScene()
            obj = scene.object.add()
            obj.method = METHOD_FILL
            obj.startTime = 0
            obj.lifeTime = life_time
            obj.fill.segment.extend(segments)

            command = bytes([0, 0, mode, slot]) + scene.SerializeToString()

            _LOGGER.info(
                "Sending custom scene: %d segment(s), mode %d, slot %d",
                len(segments), mode, slot,
            )
            _LOGGER.debug("Custom scene command: %s", command.hex())

            if await self._connection_manager.send_command(command):
                await self._refresh_scene_playback()
                _LOGGER.info("Custom scene sent successfully")
                return True

            _LOGGER.error("Failed to send custom scene command")
            return False
        except Exception as e:
            _LOGGER.error(f"Error sending custom scene: {e}")
            return False

    async def async_send_scene(
        self,
        steps: list[dict],
        mode: int = 8,
        slot: int = 0,
    ) -> bool:
        """Send a timed sequence of fills as one scene.

        The clock plays the whole thing itself at 50 FPS, so this is how to
        animate: upload a timeline rather than streaming frames. Sending fills
        one at a time cannot animate, because a scene change only takes effect
        on the clock's roughly 15 second scene cycle.
        """
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send scene")
            return False

        try:
            from .glance_pb2 import CustomScene  # type: ignore
            from .utils.led_utils import METHOD_FILL

            from .glance_pb2 import TextData  # type: ignore
            from .utils.led_utils import (
                METHOD_AREA_ANIMATION,
                METHOD_SOUND,
                METHOD_TEXT,
                METHOD_WEATHER,
            )

            scene = CustomScene()
            for step in steps:
                obj = scene.object.add()
                obj.startTime = step["at"]
                obj.lifeTime = step["frames"]
                kind = step.get("type", "fill")

                if kind == "fill":
                    obj.method = METHOD_FILL
                    obj.fill.segment.extend(step["segments"])

                elif kind == "effect":
                    # Layered onto areas already drawn in this scene; it does
                    # not draw anything on its own.
                    obj.method = METHOD_AREA_ANIMATION
                    obj.areaAnimation.type = step["effect"]
                    obj.areaAnimation.area.extend(step["segments"])
                    if step["effect"] == 0 and (
                        step["rise"] is not None or step["fall"] is not None
                    ):
                        obj.areaAnimation.pulse.riseTime = int(step["rise"] or 50)
                        obj.areaAnimation.pulse.fallTime = int(step["fall"] or 50)
                    elif step["effect"] == 1 and step["speed"] is not None:
                        obj.areaAnimation.wave.speed = int(step["speed"])
                    elif step["effect"] == 2:
                        if step["color"] is not None:
                            obj.areaAnimation.flashLight.color = step["color"]
                        if step["speed"] is not None:
                            obj.areaAnimation.flashLight.speed = int(step["speed"])

                elif kind == "text":
                    obj.method = METHOD_TEXT
                    text_data = TextData()
                    text_data.modificators = step["scroll"]
                    text_data.text = text_with_icons_to_bytes(step["text"])
                    obj.text.append(text_data)

                elif kind == "sound":
                    obj.method = METHOD_SOUND
                    obj.sound = _resolve_sound(step["sound"])

                elif kind == "weather":
                    obj.method = METHOD_WEATHER
                    obj.weather.condition = step["condition"]
                    obj.weather.position = step["position"]
                    obj.weather.intensity = step["intensity"]

            command = bytes([0, 0, mode, slot]) + scene.SerializeToString()

            _LOGGER.info(
                "Sending scene: %d step(s), %d frames total, mode %d, slot %d",
                len(steps),
                max((s["at"] + s["frames"] for s in steps), default=0),
                mode, slot,
            )
            _LOGGER.debug("Scene command: %s", command.hex())

            if await self._connection_manager.send_command(command):
                await self._refresh_scene_playback()
                _LOGGER.info("Scene sent successfully")
                return True

            _LOGGER.error("Failed to send scene command")
            return False
        except Exception as e:
            _LOGGER.error(f"Error sending scene: {e}")
            return False

    async def async_send_animation(
        self,
        animation: str,
        segment: int,
        speed: int = 3,
        mode: int = 8,
        slot: int = 0,
        life_time: int = 2500,
        back_color: int = 12,
    ) -> bool:
        """Run one of the firmware animations on the LED rings.

        The firmware animations are single-colour patterns tinted by the colour
        packed into `segment`; a colour of 0 is black and renders nothing.
        """
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send animation")
            return False

        try:
            from .glance_pb2 import CustomScene  # type: ignore
            from .utils.led_utils import (
                ANIMATION_SWEEP,
                GIF_ANIMATIONS,
                METHOD_GIF,
                METHOD_MOVING_BAR,
            )

            scene = CustomScene()
            obj = scene.object.add()
            obj.startTime = 0
            obj.lifeTime = life_time

            if animation == ANIMATION_SWEEP:
                obj.method = METHOD_MOVING_BAR
                obj.movingBar.area = segment
                # The sweep takes its colour from the bar, not the area. Only
                # the front colour is drawn -- the back colour is not rendered.
                obj.movingBar.frontColor = (segment >> 16) & 0x3F
                obj.movingBar.backColor = back_color
                obj.movingBar.speed = speed
            else:
                obj.method = METHOD_GIF
                obj.gif.type = GIF_ANIMATIONS[animation]
                obj.gif.segment = segment
                obj.gif.speed = speed

            command = bytes([0, 0, mode, slot]) + scene.SerializeToString()

            _LOGGER.info(
                "Sending animation '%s' at speed %d, mode %d, slot %d",
                animation, speed, mode, slot,
            )
            _LOGGER.debug("Animation command: %s", command.hex())

            if await self._connection_manager.send_command(command):
                await self._refresh_scene_playback()
                _LOGGER.info("Animation sent successfully")
                return True

            _LOGGER.error("Failed to send animation command")
            return False
        except Exception as e:
            _LOGGER.error(f"Error sending animation: {e}")
            return False

    async def async_delete_scene(self, slot: int = 0, refresh: bool = True) -> bool:
        """Remove the scene stored in one slot.

        `refresh` exists for the caller clearing several slots in a row, which
        only needs the display brought up to date once at the end.
        """
        if not self._connection_manager or not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot delete scene")
            return False

        try:
            if await self._connection_manager.send_command(bytes([33, 0, 0, slot])):
                if refresh:
                    await self._refresh_scene_playback()
                _LOGGER.info("Scene slot %d cleared", slot)
                return True
            _LOGGER.error("Failed to clear scene slot %d", slot)
            return False
        except Exception as e:
            _LOGGER.error(f"Error clearing scene slot: {e}")
            return False

    @staticmethod
    def _settings_to_dict(settings, raw: bytes) -> dict:
        """Decode a Settings message into the dict the entities consume.

        The raw bytes travel with it because a write has to patch the device's
        own message rather than rebuild it -- see async_write_settings.
        """
        has_dnd = settings.HasField("dnd")
        return {
            "nightModeEnabled": settings.nightModeEnabled,
            "pointsAlwaysEnabled": settings.pointsAlwaysEnabled,
            "displayBrightness": settings.displayBrightness,
            "timeModeEnable": settings.timeModeEnable,
            "timeFormat12": settings.timeFormat12,
            "permanentDND": settings.permanentDND,
            "permanentMute": settings.permanentMute,
            "dateFormat": settings.dateFormat,
            "mgrUserActivityTimeout": settings.mgrUserActivityTimeout,
            # None means no schedule is stored at all, which is different from
            # a schedule of 00:00-00:00.
            "dndRecurring": settings.dnd.recurring if has_dnd else None,
            "dndFromHour": settings.dnd.fromHour if has_dnd else None,
            "dndTillHour": settings.dnd.tillHour if has_dnd else None,
            RAW_SETTINGS_KEY: bytes(raw),
        }

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
                    # mgrUserActivityTimeout is deliberately absent. Devices
                    # that do not report it use a firmware default; writing an
                    # explicit value here has been observed to stop the rim
                    # points staying lit.
                }
                _LOGGER.debug("Using default settings as base")

            settings = Settings()

            raw_settings = current_settings.get(RAW_SETTINGS_KEY)
            if raw_settings:
                # Start from the device's own message rather than a blank one.
                # Parsing preserves every field it contains, including the
                # nested DND schedule and any field this schema does not know
                # about, and re-serialising is byte-identical when nothing is
                # changed. Building a fresh Settings() instead would drop them.
                settings.ParseFromString(raw_settings)
            else:
                # No successful read to build on. Fall back to the previous
                # behaviour, but only for the fields we actually have values
                # for -- writing defaults for the rest is what corrupted
                # devices before.
                _LOGGER.warning(
                    "Writing settings without a prior read; fields not modelled "
                    "by this integration cannot be preserved"
                )
                for key in SETTINGS_FIELD_NAMES:
                    if key in current_settings:
                        setattr(settings, key, current_settings[key])

            # Apply only what the caller asked to change.
            dnd_changes = {
                DND_FIELD_NAMES[key]: value
                for key, value in settings_data.items()
                if key in DND_FIELD_NAMES
            }
            for key, value in settings_data.items():
                if key in DND_FIELD_NAMES:
                    continue
                if key not in SETTINGS_FIELD_NAMES:
                    _LOGGER.warning("Ignoring unknown setting %s", key)
                    continue
                setattr(settings, key, value)

            if dnd_changes:
                # All three DND fields are `required` in the schema, so a
                # partially populated submessage will not serialise. When the
                # device has no schedule yet, fill the gaps rather than fail.
                if not settings.HasField("dnd"):
                    dnd_changes.setdefault("recurring", True)
                    dnd_changes.setdefault("fromHour", 0)
                    dnd_changes.setdefault("tillHour", 0)
                for field, value in dnd_changes.items():
                    setattr(settings.dnd, field, value)

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

                # Make the cache reflect what was just written. Without this the
                # next write within the cache lifetime starts from pre-write
                # bytes and silently reverts this change -- two settings changed
                # in quick succession would fight each other.
                if self._connection_manager:
                    self._connection_manager.cache_settings(
                        self._settings_to_dict(settings, settings_bytes)
                    )

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
        template: bytes | None = None,
        unit: str = "C",
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
            
            # Thermometer icon, the current value, then the degree sign and the
            # unit letter. Home Assistant has already converted the numbers to
            # whatever the user's system uses, so only the letter changes here --
            # converting again would double-convert.
            if template is None:
                letter = ord("F") if str(unit).upper().endswith("F") else ord("C")
                default_template = bytes([194, 143, 8, 194, 176, letter])
                template = default_template
                _LOGGER.info(
                    "Using default template in degrees %s: %s",
                    chr(letter), template.hex(),
                )
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


class GlanceClockNotifyEntity(NotifyEntity):
    """A notify entity, so the clock can be a target like any phone.

    Home Assistant's modern notify platform carries a message and a title and
    nothing else, which is the right shape for a phone and a poor fit for a
    clock that can pick a sound, an animation and a colour. Those ride in the
    message as markers instead -- see utils/notice_markers.py for why title was
    not overloaded to mean one of them.

    This does not replace glance_clock.send_notice. That service reaches
    everything the firmware has, and it is what an automation written for the
    clock should use. This is for the automations written for everything.
    """

    _attr_supported_features = NotifyEntityFeature.TITLE
    _attr_icon = "mdi:clock-alert-outline"

    def __init__(self, entry: ConfigEntry, config_data: dict, service) -> None:
        """Initialize the notify entity."""
        self._entry = entry
        self._service = service
        self._mac_address = config_data.get("mac_address")
        self._attr_name = None  # the device's own name is enough
        self._attr_unique_id = f"{self._mac_address}_notify"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._mac_address)},
            connections={("bluetooth", self._mac_address)},
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Show a message, applying any settings its markers carry."""
        from .services.notice import resolve_notice
        from .utils.notice_markers import extract_notice_options

        text, options = extract_notice_options(message or "")

        # Title first, the way the old legacy path composed it. A generic
        # sender uses it as a title and gets one; nothing here reinterprets it.
        if title:
            text = f"{title}: {text}" if text else title

        if not text:
            _LOGGER.warning("Cannot send an empty notification")
            return

        try:
            notice = resolve_notice(options)
        except (ValueError, TypeError) as err:
            # A marker naming a colour or sound the firmware does not have.
            # Raised so it reaches the caller rather than dying in the log.
            raise ServiceValidationError(f"notify: {err}") from err

        await self._service.async_send_notice(text=text, **notice)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> bool:
    """Set up the Glance Clock notification service and its notify entity."""
    config_data = hass.data[DOMAIN][entry.entry_id]

    # This object is the integration's command layer, not a notify platform:
    # send_notice, set_leds, set_scene and the rest all reach the clock through
    # it. It lives here for historical reasons, which is why Platform.NOTIFY
    # cannot simply be dropped.
    notify_service = GlanceClockNotificationService(config_data)

    # Store the service for access by entities
    if DOMAIN + "_notify" not in hass.data:
        hass.data[DOMAIN + "_notify"] = {}
    hass.data[DOMAIN + "_notify"][entry.entry_id] = notify_service

    # And now an actual entity, so notify.send_message has something to target.
    # Until 1.27.0 this platform added none, so notify.<clock> did not exist
    # while the README insisted it did.
    async_add_entities([GlanceClockNotifyEntity(entry, config_data, notify_service)])

    _LOGGER.info(
        f"Glance Clock notification service set up for {config_data.get('name')}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the notification service."""
    if DOMAIN + "_notify" in hass.data:
        hass.data[DOMAIN + "_notify"].pop(entry.entry_id, None)
    return True
