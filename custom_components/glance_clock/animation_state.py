"""Shared state for the animation controls on the device page.

The animation selects and the speed number describe what to send; the run
button sends it. None of it lives on the clock -- the device has no notion of
"a pending animation" -- so the chosen values are kept here, per config entry,
and restored across restarts by the entities themselves.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DOMAIN

STATE_KEY = "animation_state"

DEFAULTS = {
    "animation": "fire",
    # White rather than black: black is a valid colour that renders nothing,
    # which looks exactly like a broken integration.
    "color": "white",
    "speed": 3,
    "sound": "bells",
    # Slot 0 by default, which is where the animation buttons have always
    # written. Slot 1 belongs to send_forecast, so anyone putting a second
    # animation somewhere should reach for 2 and up.
    "slot": 0,
}


def get_animation_state(hass: HomeAssistant, entry_id: str) -> dict:
    """Return the mutable animation state for a config entry."""
    entry_data = hass.data.setdefault(DOMAIN, {}).setdefault(entry_id, {})
    return entry_data.setdefault(STATE_KEY, dict(DEFAULTS))
