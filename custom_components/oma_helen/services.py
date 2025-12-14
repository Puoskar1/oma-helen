from __future__ import annotations

from datetime import date
import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall

from .const import (
    ATTR_END_DATE,
    ATTR_START_DATE,
    DATA_COORDINATOR,
    DOMAIN,
    SERVICE_REFRESH_STATISTICS,
)

_LOGGER = logging.getLogger(__name__)

_SERVICE_FLAG = "services_registered"


async def async_setup_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_SERVICE_FLAG):
        return

    async def _handle_refresh(call: ServiceCall) -> None:
        start = date.fromisoformat(call.data[ATTR_START_DATE])
        end = date.fromisoformat(call.data[ATTR_END_DATE])
        if end < start:
            raise vol.Invalid("end_date must be on or after start_date")

        entries = hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
            await coordinator.async_refresh_range(start, end)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_STATISTICS,
        _handle_refresh,
        schema=vol.Schema(
            {
                vol.Required(ATTR_START_DATE): str,
                vol.Required(ATTR_END_DATE): str,
            }
        ),
    )
    domain_data[_SERVICE_FLAG] = True


async def async_unload_services(hass: HomeAssistant) -> None:
    domain_data = hass.data.get(DOMAIN)
    if not domain_data or not domain_data.get(_SERVICE_FLAG):
        return

    if hass.config_entries.async_entries(DOMAIN):
        return

    hass.services.async_remove(DOMAIN, SERVICE_REFRESH_STATISTICS)
    domain_data[_SERVICE_FLAG] = False

