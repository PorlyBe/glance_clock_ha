"""Button platform for Glance Clock."""
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .animation_state import get_animation_state
from .const import DOMAIN
from .entity import GlanceClockEntity
from .utils.led_utils import (
    EFFECTS,
    PIXELS_PER_RING,
    RING_COUNT,
    check_speed,
    pack_segment,
    resolve_animation,
    scene_steps_from_config,
)

_LOGGER = logging.getLogger(__name__)

# Hand calibration. The clock tracks its hands by counting motor steps from a
# reference position; it has no idea where they physically are. HOMING_START
# drives them to what it believes is 12:00 and holds them there, and
# HOMING_CONFIRM accepts wherever they are as the new reference.
HOMING_START = 43
HOMING_CONFIRM = 44

# How long an effect runs from the Run button. Matches the fifty seconds the
# firmware animations get, so switching between them feels the same.
EFFECT_SECONDS = 50


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Glance Clock button entities."""
    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    mac_address = entry_data["mac_address"]
    name = entry_data["name"]
    connection_manager = entry_data["connection_manager"]

    async_add_entities(
        [
            GlanceClockCalibrateHandsButton(
                config_entry, mac_address, name, connection_manager),
            GlanceClockConfirmHandsButton(
                config_entry, mac_address, name, connection_manager),
            GlanceClockRunAnimationButton(
                config_entry, mac_address, name, connection_manager),
            GlanceClockStopAnimationButton(
                config_entry, mac_address, name, connection_manager),
            GlanceClockPlaySoundButton(
                config_entry, mac_address, name, connection_manager),
            GlanceClockClearAllScenesButton(
                config_entry, mac_address, name, connection_manager),
        ]
    )


class GlanceClockButtonBase(GlanceClockEntity, ButtonEntity):
    """Base for the clock's buttons, keeping availability honest.

    Buttons do not poll, so `available` is only re-evaluated when the entity
    writes its state. Without this, a button set up while the clock was still
    connecting stays greyed out until something unrelated happens to wake it --
    the button works, it just looks broken. Writing state when the connection
    comes up is all it takes.
    """

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._connection_manager:
            self._connection_manager.add_connection_callback(
                self._on_connection_established)

    async def async_will_remove_from_hass(self) -> None:
        if self._connection_manager:
            self._connection_manager.remove_connection_callback(
                self._on_connection_established)
        await super().async_will_remove_from_hass()

    async def _on_connection_established(self) -> None:
        """Re-evaluate availability now that the clock is reachable."""
        self.async_write_ha_state()


class GlanceClockCommandButton(GlanceClockButtonBase):
    """A button that sends one payload-less command to the clock."""

    _command: int

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._connection_manager.is_connected

    async def async_press(self) -> None:
        """Send the command."""
        if not self._connection_manager.is_connected:
            _LOGGER.warning("Device not connected, cannot send %s", self.name)
            return

        # Padded to four bytes. Trailing zeroes may be omitted per the protocol
        # notes, but this is the form verified against hardware.
        command = bytes([self._command, 0, 0, 0])
        if await self._connection_manager.send_command(command):
            _LOGGER.info("%s sent", self.name)
        else:
            _LOGGER.error("Failed to send %s", self.name)


class GlanceClockCalibrateHandsButton(GlanceClockCommandButton):
    """Step one of hand calibration: drive the hands to the 12:00 reference."""

    _command = HOMING_START

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the calibrate hands button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Calibrate Hands"
        self._attr_unique_id = f"{mac_address}_calibrate_hands"
        self._attr_icon = "mdi:clock-edit-outline"


class GlanceClockConfirmHandsButton(GlanceClockCommandButton):
    """Step two of hand calibration: accept the current position as 12:00.

    Press this only once the hands physically point straight up. If one of them
    is off, pull it off its spindle and reseat it first -- never twist a hand
    while it is seated, that drives the gear train and can move the reference
    the clock just found.
    """

    _command = HOMING_CONFIRM

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the confirm hand position button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        # Names the precondition rather than the action: pressing this while the
        # hands are anywhere but straight up teaches the clock a wrong reference.
        self._attr_name = f"{device_name} Confirm Hand Positions at 12"
        self._attr_unique_id = f"{mac_address}_confirm_hand_position"
        self._attr_icon = "mdi:check-decagram-outline"


#: Where the animation buttons write when nothing else is chosen. The Animation
#: Slot number on the device page overrides it, so several animations can be
#: parked at once; this is only the fallback if that state is missing.
ANIMATION_SLOT = 0

#: Slots the firmware has, 0-7. Everything the services accept is bounded by
#: this, so clearing all of them needs no bookkeeping of what was used.
SCENE_SLOTS = 8

#: Watchface: the animation and the digital time show at once. Verified on
#: hardware -- mode 24 alternates between them instead.
ANIMATION_MODE = 8


class GlanceClockRunAnimationButton(GlanceClockButtonBase):
    """Send the animation chosen by the animation selects and speed slider.

    Named "Animation Run" rather than "Run Animation" so all the animation
    controls sort together in the UI.
    """

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the run animation button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Animation Run"
        self._attr_unique_id = f"{mac_address}_run_animation"
        self._attr_icon = "mdi:play-circle-outline"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._connection_manager.is_connected

    async def async_press(self) -> None:
        """Pack the chosen settings and send them."""
        state = get_animation_state(self.hass, self._config_entry.entry_id)
        choice = str(state["animation"]).strip().lower()

        if choice in EFFECTS:
            await self._run_effect(choice, state)
            return

        try:
            animation = resolve_animation(state["animation"])
            speed = check_speed(animation, state["speed"])
            segment = pack_segment(
                0,
                state["color"],
                length=PIXELS_PER_RING,
                ring=0,
                rings_tall=RING_COUNT,
            )
        except ValueError as err:
            # Most likely a negative speed on an animation that has no
            # direction. Raised rather than logged: a message in the log is a
            # message nobody reads, and the press otherwise looks successful.
            raise ServiceValidationError(f"Cannot run animation: {err}") from err

        notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(
            self._config_entry.entry_id
        )
        if not notify_service:
            _LOGGER.error("Notification service not available for animations")
            return

        if self._connection_manager and not hasattr(notify_service, "_connection_manager"):
            notify_service._connection_manager = self._connection_manager

        await notify_service.async_send_animation(
            animation,
            segment,
            speed=speed,
            mode=ANIMATION_MODE,
            slot=int(state.get("slot", ANIMATION_SLOT)),
        )

    async def _run_effect(self, effect: str, state: dict) -> None:
        """Play one of the three effects over the whole ring.

        An effect modulates an area that is already lit rather than drawing
        anything, so the area has to be filled first and the effect chained
        after it -- overlapping the two lets the fill hold the area at a
        constant colour and swallow the effect entirely.
        """
        colour = state["color"]
        try:
            speed = check_speed(effect, state["speed"])
            steps = scene_steps_from_config(
                [
                    {
                        "type": "fill", "seconds": 0.5,
                        "start": 0, "length": PIXELS_PER_RING,
                        "ring": 0, "rings_tall": RING_COUNT, "color": colour,
                    },
                    {
                        "type": "effect", "seconds": EFFECT_SECONDS,
                        "effect": effect, "speed": speed, "color": colour,
                        "start": 0, "length": PIXELS_PER_RING,
                        "ring": 0, "rings_tall": RING_COUNT,
                    },
                ]
            )
        except ValueError as err:
            raise ServiceValidationError(f"Cannot run effect: {err}") from err

        notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(
            self._config_entry.entry_id
        )
        if not notify_service:
            _LOGGER.error("Notification service not available for animations")
            return

        if self._connection_manager and not hasattr(notify_service, "_connection_manager"):
            notify_service._connection_manager = self._connection_manager

        await notify_service.async_send_scene(
            steps,
            mode=ANIMATION_MODE,
            slot=int(state.get("slot", ANIMATION_SLOT)),
        )


class GlanceClockStopAnimationButton(GlanceClockButtonBase):
    """Clear whatever the Run Animation button last sent."""

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the stop animation button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Animation Stop"
        self._attr_unique_id = f"{mac_address}_stop_animation"
        self._attr_icon = "mdi:stop-circle-outline"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._connection_manager.is_connected

    async def async_press(self) -> None:
        """Delete the animation slot."""
        notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(
            self._config_entry.entry_id
        )
        if not notify_service:
            _LOGGER.error("Notification service not available for animations")
            return

        if self._connection_manager and not hasattr(notify_service, "_connection_manager"):
            notify_service._connection_manager = self._connection_manager

        # Whichever slot Animation Run is pointed at, so Stop undoes what Run
        # just did rather than always clearing slot 0.
        state = get_animation_state(self.hass, self._config_entry.entry_id)
        await notify_service.async_delete_scene(int(state.get("slot", ANIMATION_SLOT)))


class GlanceClockClearAllScenesButton(GlanceClockButtonBase):
    """Empty every scene slot, whoever filled it.

    The way out when the clock is displaying something you no longer have the
    call for. A scene stays in its slot and replays until it is cleared, so an
    experiment that went wrong keeps going wrong on the wall until somebody
    remembers which slot it went into -- and the slot number is exactly the
    thing nobody writes down.
    """

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the clear all scenes button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Clear All Scenes"
        self._attr_unique_id = f"{mac_address}_clear_all_scenes"
        self._attr_icon = "mdi:layers-remove"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._connection_manager.is_connected

    async def async_press(self) -> None:
        """Delete every slot the firmware has."""
        notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(
            self._config_entry.entry_id
        )
        if not notify_service:
            _LOGGER.error("Notification service not available for scenes")
            return

        if self._connection_manager and not hasattr(notify_service, "_connection_manager"):
            notify_service._connection_manager = self._connection_manager

        # Every slot, one at a time, carrying on past a failure: a slot that
        # refuses is no reason to leave the other seven filled, and clearing an
        # empty slot is harmless. Only the last one asks the clock to redraw --
        # eight refreshes would be seven commands spent on intermediate states
        # nobody sees.
        for slot in range(SCENE_SLOTS):
            try:
                await notify_service.async_delete_scene(
                    slot, refresh=slot == SCENE_SLOTS - 1
                )
            except Exception as err:  # noqa: BLE001 -- bleak raises broadly
                _LOGGER.warning("Could not clear scene slot %d: %s", slot, err)


class GlanceClockPlaySoundButton(GlanceClockButtonBase):
    """Play the sound chosen by the Sound select.

    Sent as a notice rather than a scene: notices are immediate, while a scene
    only takes effect on the clock's roughly 15 second cycle -- useless for
    auditioning sounds. The sound's name is shown while it plays, so stepping
    through the list tells you which is which.
    """

    def __init__(self, config_entry, mac_address, device_name, connection_manager):
        """Initialize the play sound button."""
        super().__init__(config_entry, mac_address, device_name, connection_manager)
        self._attr_name = f"{device_name} Sound Play"
        self._attr_unique_id = f"{mac_address}_play_sound"
        self._attr_icon = "mdi:play-speed"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._connection_manager.is_connected

    async def async_press(self) -> None:
        """Play the selected sound."""
        from .const import SOUNDS

        name = get_animation_state(self.hass, self._config_entry.entry_id)["sound"]
        if name not in SOUNDS:
            _LOGGER.error("Unknown sound '%s'", name)
            return

        notify_service = self.hass.data.get(DOMAIN + "_notify", {}).get(
            self._config_entry.entry_id
        )
        if not notify_service:
            _LOGGER.error("Notification service not available for sounds")
            return

        if self._connection_manager and not hasattr(notify_service, "_connection_manager"):
            notify_service._connection_manager = self._connection_manager

        await notify_service.async_send_notice(
            text=name.replace("_", " ").upper(),
            animation=0,   # no ring animation; this is about the sound
            sound=SOUNDS[name],
        )
