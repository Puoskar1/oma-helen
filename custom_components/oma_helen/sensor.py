from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DELIVERY_SITE_ID, DATA_COORDINATOR, DOMAIN
from .coordinator import OmaHelenCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OmaHelenCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        [
            OmaHelenLastImportSensor(coordinator, entry),
            OmaHelenSpotPriceSensor(coordinator, entry),
        ]
    )


class _BaseOmaHelenSensor(CoordinatorEntity[OmaHelenCoordinator], SensorEntity):
    def __init__(self, coordinator: OmaHelenCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._delivery_site_id = str(entry.data[CONF_DELIVERY_SITE_ID])

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._delivery_site_id)},
            name=f"Oma Helen {self._delivery_site_id}",
            manufacturer="Helen",
        )


class OmaHelenLastImportSensor(_BaseOmaHelenSensor):
    _attr_icon = "mdi:calendar-check"
    _attr_has_entity_name = True
    _attr_name = "Last import date"
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, coordinator: OmaHelenCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._delivery_site_id}_last_import_date"

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        imported = self.coordinator.data.last_imported_date
        return imported


class OmaHelenSpotPriceSensor(_BaseOmaHelenSensor):
    _attr_icon = "mdi:currency-eur"
    _attr_has_entity_name = True
    _attr_name = "Last spot price"

    def __init__(self, coordinator: OmaHelenCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._delivery_site_id}_last_spot_price"

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "EUR/kWh"

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.last_spot_price_eur_per_kwh
