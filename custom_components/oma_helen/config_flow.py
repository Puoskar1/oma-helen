from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import api
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BACKFILL_DAYS,
    CONF_DELIVERY_SITE_ID,
    CONF_ENABLE_COST,
    CONF_INITIAL_BACKFILL_DONE,
    DEFAULT_BACKFILL_DAYS,
    DOMAIN,
)


@dataclass(slots=True)
class _PendingSetup:
    access_token: str
    backfill_days: int
    enable_cost: bool
    delivery_site_ids: list[str]


class OmaHelenConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    _pending: _PendingSetup | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            backfill_days = int(user_input[CONF_BACKFILL_DAYS])
            enable_cost = bool(user_input[CONF_ENABLE_COST])

            try:
                login_result = await self.hass.async_add_executor_job(api.login, username, password)
            except api.OmaHelenAuthError:
                errors["base"] = "auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                self._pending = _PendingSetup(
                    access_token=login_result.access_token,
                    backfill_days=backfill_days,
                    enable_cost=enable_cost,
                    delivery_site_ids=login_result.delivery_site_ids,
                )

                if len(login_result.delivery_site_ids) == 1:
                    return await self._async_create_entry(login_result.delivery_site_ids[0])
                return await self.async_step_select_site()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(CONF_BACKFILL_DAYS, default=DEFAULT_BACKFILL_DAYS): vol.Coerce(int),
                vol.Optional(CONF_ENABLE_COST, default=False): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_select_site(self, user_input: dict[str, Any] | None = None):
        if not self._pending:
            return self.async_abort(reason="unknown")

        errors: dict[str, str] = {}
        if user_input is not None:
            return await self._async_create_entry(user_input[CONF_DELIVERY_SITE_ID])

        options = {site_id: site_id for site_id in self._pending.delivery_site_ids}
        data_schema = vol.Schema(
            {
                vol.Required(CONF_DELIVERY_SITE_ID): vol.In(options),
            }
        )
        return self.async_show_form(step_id="select_site", data_schema=data_schema, errors=errors)

    async def _async_create_entry(self, delivery_site_id: str):
        if not self._pending:
            return self.async_abort(reason="unknown")

        await self.async_set_unique_id(delivery_site_id)
        self._abort_if_unique_id_configured()

        data = {
            CONF_ACCESS_TOKEN: self._pending.access_token,
            CONF_DELIVERY_SITE_ID: delivery_site_id,
            CONF_BACKFILL_DAYS: self._pending.backfill_days,
            CONF_ENABLE_COST: self._pending.enable_cost,
            CONF_INITIAL_BACKFILL_DONE: False,
        }
        title = f"Oma Helen {delivery_site_id}"
        return self.async_create_entry(title=title, data=data)

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None):
        entry_id = self.context.get("entry_id")
        if entry_id:
            self.context["reauth_entry_id"] = entry_id
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                login_result = await self.hass.async_add_executor_job(api.login, username, password)
            except api.OmaHelenAuthError:
                errors["base"] = "auth"
            except Exception:
                errors["base"] = "unknown"
            else:
                entry = self.hass.config_entries.async_get_entry(self.context["reauth_entry_id"])
                if entry is not None:
                    new_data = dict(entry.data)
                    new_data[CONF_ACCESS_TOKEN] = login_result.access_token
                    self.hass.config_entries.async_update_entry(entry, data=new_data)
                    await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        data_schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=data_schema,
            errors=errors,
        )

