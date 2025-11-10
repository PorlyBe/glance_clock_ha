"""
Options flow for Glance Clock integration.
"""

from __future__ import annotations

from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN

class GlanceClockOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Glance Clock."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        # Home Assistant instance is available as self.hass in OptionsFlow


    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        # Always start with calibration step
        return await self.async_step_calibration(user_input)

    async def async_step_calibration(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            action = user_input.get("action")
            if action == "start":
                await self._send_calibration_command(43)
                return self.async_show_form(
                    step_id="calibration",
                    data_schema=vol.Schema({
                        vol.Optional("action", default="confirm"): vol.In({"confirm": "Confirm Calibration"})
                    }),
                    description_placeholders={
                        "info": ""
                    },
                )
            elif action == "confirm":
                await self._send_calibration_command(44)
                return self.async_show_form(
                    step_id="done",
                    data_schema=vol.Schema({}),
                    description_placeholders={
                        "done": ""
                    },
                )

        # Initial calibration form
        return self.async_show_form(
            step_id="calibration",
            data_schema=vol.Schema({
                vol.Optional("action", default="start"): vol.In({"start": "Start Calibration"})
            }),
            description_placeholders={
                "info": ""
            },
        )

    async def _send_calibration_command(self, command_byte: int):
        # Get Home Assistant instance and config entry
        hass = self.hass
        entry_id = self.config_entry.entry_id
        # Get notify service
        notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry_id)
        if notify_service and hasattr(notify_service, "_connection_manager"):
            await notify_service._connection_manager.send_command(bytes([command_byte]))
        else:
            import logging
            logging.getLogger(__name__).warning("Could not send calibration command: notify service or connection manager missing.")
