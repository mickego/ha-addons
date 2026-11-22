"""Konfigurationsflöde: bekräfta add-onets adress (förifylld)."""
from __future__ import annotations

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_URL, DOMAIN

CONF_URL = "url"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(f"{url}/api/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    resp.raise_for_status()
                    await resp.json()
            except Exception:  # noqa: BLE001
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="Reminders Pro", data={CONF_URL: url})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_URL, default=DEFAULT_URL): str}),
            errors=errors,
        )
