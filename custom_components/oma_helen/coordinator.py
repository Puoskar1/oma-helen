from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging

from helenservice.const import RESOLUTION_QUARTER

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import api
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BACKFILL_DAYS,
    CONF_DELIVERY_SITE_ID,
    CONF_ENABLE_COST,
    CONF_INITIAL_BACKFILL_DONE,
    CONF_LAST_FETCHED_DATE,
    CONF_LAST_SUM_COST,
    CONF_LAST_SUM_KWH,
    DOMAIN,
    STATS_SOURCE,
)
from .statistics import (
    ConsumptionAndCostPoint,
    build_cost_statistic_id,
    build_consumption_statistic_id,
    build_statistics,
    insert_statistics,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CoordinatorData:
    last_imported_date: date | None
    last_interval_start: datetime | None
    last_spot_price_eur_per_kwh: float | None


class OmaHelenCoordinator(DataUpdateCoordinator[CoordinatorData]):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, update_interval: timedelta
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}:{entry.entry_id}",
            update_interval=update_interval,
        )
        self.entry = entry

    async def async_refresh_range(self, start: date, end: date) -> None:
        await self._async_fetch_and_insert(start, end, force_overwrite=True)

    async def _async_update_data(self) -> CoordinatorData:
        today_local = dt_util.now().date()
        yesterday_local = today_local - timedelta(days=1)

        initial_done = bool(self.entry.data.get(CONF_INITIAL_BACKFILL_DONE, False))
        last_fetched_str: str | None = self.entry.data.get(CONF_LAST_FETCHED_DATE)
        last_fetched = date.fromisoformat(last_fetched_str) if last_fetched_str else None

        if not initial_done:
            backfill_days = int(self.entry.data.get(CONF_BACKFILL_DAYS, 0))
            start = today_local - timedelta(days=backfill_days)
            end = yesterday_local
        else:
            start = (last_fetched + timedelta(days=1)) if last_fetched else yesterday_local
            end = yesterday_local

        if end < start:
            return CoordinatorData(
                last_imported_date=last_fetched,
                last_interval_start=None,
                last_spot_price_eur_per_kwh=None,
            )

        return await self._async_fetch_and_insert(start, end, force_overwrite=False)

    async def _async_fetch_and_insert(
        self, start: date, end: date, force_overwrite: bool
    ) -> CoordinatorData:
        access_token: str = self.entry.data[CONF_ACCESS_TOKEN]
        delivery_site_id: str = self.entry.data[CONF_DELIVERY_SITE_ID]
        enable_cost: bool = bool(self.entry.data.get(CONF_ENABLE_COST, False))

        try:
            client = await self.hass.async_add_executor_job(
                api.build_client, access_token, delivery_site_id
            )
        except api.OmaHelenDeliverySiteError as exc:
            raise UpdateFailed("Invalid delivery site") from exc
        except Exception as exc:
            raise UpdateFailed("Failed to initialize API client") from exc

        try:
            response = await self.hass.async_add_executor_job(
                api.get_measurements_with_spot_prices,
                client,
                start,
                end,
                RESOLUTION_QUARTER,
            )
        except Exception as exc:
            raise UpdateFailed("Failed to fetch measurements") from exc

        points = _response_to_points(response)
        if not points:
            _LOGGER.warning("No measurement points returned for %s to %s", start, end)
            return CoordinatorData(
                last_imported_date=end,
                last_interval_start=None,
                last_spot_price_eur_per_kwh=None,
            )

        consumption_statistic_id = build_consumption_statistic_id(delivery_site_id)
        cost_statistic_id = build_cost_statistic_id(delivery_site_id) if enable_cost else None

        last_sum_kwh = float(self.entry.data.get(CONF_LAST_SUM_KWH, 0.0))
        last_sum_cost = float(self.entry.data.get(CONF_LAST_SUM_COST, 0.0))

        consumption_stats, cost_stats, last_values = build_statistics(
            self.hass,
            consumption_statistic_id,
            cost_statistic_id,
            points,
            last_sum_kwh=last_sum_kwh,
            last_sum_cost=last_sum_cost,
            include_cost=enable_cost,
        )

        try:
            await insert_statistics(
                self.hass,
                consumption_stats,
                cost_stats,
                force_overwrite=force_overwrite,
            )
        except ConfigEntryAuthFailed:
            raise
        except Exception as exc:
            raise UpdateFailed("Failed to write statistics") from exc

        await self._async_persist_progress(
            last_imported_date=end,
            last_sum_kwh=last_values.last_sum_kwh,
            last_sum_cost=last_values.last_sum_cost,
        )

        return CoordinatorData(
            last_imported_date=end,
            last_interval_start=last_values.last_interval_start,
            last_spot_price_eur_per_kwh=last_values.last_spot_price_eur_per_kwh,
        )

    async def _async_persist_progress(
        self, last_imported_date: date, last_sum_kwh: float, last_sum_cost: float
    ) -> None:
        new_data = dict(self.entry.data)
        new_data[CONF_LAST_FETCHED_DATE] = last_imported_date.isoformat()
        new_data[CONF_INITIAL_BACKFILL_DONE] = True
        new_data[CONF_LAST_SUM_KWH] = last_sum_kwh
        new_data[CONF_LAST_SUM_COST] = last_sum_cost
        self.hass.config_entries.async_update_entry(self.entry, data=new_data)


def _parse_ts(value: str) -> datetime:
    ts = value.rstrip()
    if ts.endswith("Z"):
        ts = f"{ts[:-1]}+00:00"
    parsed = datetime.fromisoformat(ts)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.UTC)
    return dt_util.as_utc(parsed)


def _response_to_points(response) -> list[ConsumptionAndCostPoint]:
    points: list[ConsumptionAndCostPoint] = []
    for s in getattr(response, "series", []) or []:
        if s.electricity is None:
            continue
        start = _parse_ts(s.start)
        consumption_kwh = abs(float(s.electricity))
        spot_c_per_kwh = None
        if s.electricity_spot_prices_vat is not None:
            spot_c_per_kwh = float(s.electricity_spot_prices_vat)
        elif s.electricity_spot_prices is not None:
            spot_c_per_kwh = float(s.electricity_spot_prices)

        points.append(
            ConsumptionAndCostPoint(
                start=start,
                consumption_kwh=consumption_kwh,
                spot_price_c_per_kwh=spot_c_per_kwh,
            )
        )
    points.sort(key=lambda p: p.start)
    return points
