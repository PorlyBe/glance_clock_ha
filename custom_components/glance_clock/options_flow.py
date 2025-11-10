"""
Options flow for Glance Clock integration.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN


class GlanceClockOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for the integration."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options - show action menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["calibration", "clear_scenes"]
        )

    async def async_step_calibration(self, user_input=None):
        """Start calibration process."""
        if user_input is not None:
            # Send dummy calibration command
            await self._send_calibration_command(43)
            return await self.async_step_confirm_calibration()

        return self.async_show_form(
            step_id="calibration",
            data_schema=vol.Schema({}),
            description_placeholders={},
        )

    async def async_step_confirm_calibration(self, user_input=None):
        """Confirm calibration step."""
        if user_input is not None:
            await self._send_calibration_command(44)
            return await self.async_step_done_calibration()

        return self.async_show_form(
            step_id="confirm_calibration",
            data_schema=vol.Schema({}),
            description_placeholders={},
        )

    async def async_step_done_calibration(self, user_input=None):
        """Final step - show calibration completion."""
        return self.async_create_entry(title="", data={})

    async def async_step_clear_scenes(self, user_input=None):
        """Clear scenes process."""
        if user_input is not None:
            # Send dummy clear scenes command
            await self._send_clear_scenes_command()
            return await self.async_step_done_clear_scenes()

        return self.async_show_form(
            step_id="clear_scenes",
            data_schema=vol.Schema({}),
            description_placeholders={},
        )

    async def async_step_done_clear_scenes(self, user_input=None):
        """Final step - show clear scenes completion."""
        return self.async_create_entry(title="", data={})

    async def _send_clear_scenes_command(self):
        """Send clear scenes command (dummy implementation)."""
        # TODO: Replace with actual clear scenes command
        # Example: await self.hass.async_add_executor_job(clear_scenes)
        pass

    async def _send_calibration_command(self, command_byte: int):
        hass = self.hass
        entry_id = self.config_entry.entry_id
        notify_service = hass.data.get(DOMAIN + "_notify", {}).get(entry_id)
        if notify_service and hasattr(notify_service, "_connection_manager"):
            await notify_service._connection_manager.send_command(bytes([command_byte]))
        else:
            import logging
            logging.getLogger(__name__).warning(
                "Could not send calibration command: notify service or connection manager missing.")
        pass
