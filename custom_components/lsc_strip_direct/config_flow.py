"""Config flow: name, IP, device id, local key."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from . import client
from .const import (
    CONF_DEVICE_ID,
    CONF_HOST,
    CONF_LOCAL_KEY,
    CONF_SCENE_DP,
    CONF_VERSION,
    DEFAULT_SCENE_DP,
    DEFAULT_VERSION,
    DOMAIN,
    VERSIONS,
)


class LscStripDirectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry):
        return LscStripOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            user_input = {k: (v.strip() if isinstance(v, str) else v) for k, v in user_input.items()}
            await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
            self._abort_if_unique_id_configured()
            err = await self.hass.async_add_executor_job(
                client.test_connection,
                user_input[CONF_DEVICE_ID],
                user_input[CONF_HOST],
                user_input[CONF_LOCAL_KEY],
                user_input[CONF_VERSION],
            )
            if err is None:
                return self.async_create_entry(title=user_input["name"], data=user_input)
            errors["base"] = "cannot_connect"
            placeholders["error"] = err

        d = user_input or {}
        schema = vol.Schema(
            {
                vol.Required("name", default=d.get("name", "")): str,
                vol.Required(CONF_HOST, default=d.get(CONF_HOST, "")): str,
                vol.Required(CONF_DEVICE_ID, default=d.get(CONF_DEVICE_ID, "")): str,
                vol.Required(CONF_LOCAL_KEY, default=d.get(CONF_LOCAL_KEY, "")): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_VERSION, default=d.get(CONF_VERSION, DEFAULT_VERSION)): vol.In(VERSIONS),
                vol.Required(CONF_SCENE_DP, default=d.get(CONF_SCENE_DP, DEFAULT_SCENE_DP)): int,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors, description_placeholders=placeholders
        )


class LscStripOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        cur = self.config_entry.options.get(
            CONF_SCENE_DP, self.config_entry.data.get(CONF_SCENE_DP, DEFAULT_SCENE_DP)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_SCENE_DP, default=cur): int}),
        )
