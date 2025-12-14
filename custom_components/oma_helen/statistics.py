from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import STATS_SOURCE

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ConsumptionAndCostPoint:
    start: datetime
    consumption_kwh: float
    spot_price_c_per_kwh: float | None


@dataclass(frozen=True, slots=True)
class _LastValues:
    last_interval_start: datetime | None
    last_spot_price_eur_per_kwh: float | None
    last_sum_kwh: float
    last_sum_cost: float


def build_consumption_statistic_id(delivery_site_id: str) -> str:
    return f"{STATS_SOURCE}:{delivery_site_id}:consumption"


def build_cost_statistic_id(delivery_site_id: str) -> str:
    return f"{STATS_SOURCE}:{delivery_site_id}:cost"


def _spot_to_eur_per_kwh(spot_price_c_per_kwh: float | None) -> float | None:
    if spot_price_c_per_kwh is None:
        return None
    return spot_price_c_per_kwh / 100.0


def build_statistics(
    hass: HomeAssistant,
    consumption_statistic_id: str,
    cost_statistic_id: str | None,
    points: list[ConsumptionAndCostPoint],
    *,
    last_sum_kwh: float,
    last_sum_cost: float,
    include_cost: bool,
):
    from homeassistant.components.recorder.statistics import StatisticData, StatisticMetaData

    consumption_meta = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name="Oma Helen consumption",
        source=STATS_SOURCE,
        statistic_id=consumption_statistic_id,
        unit_of_measurement="kWh",
    )

    cost_meta = None
    if include_cost and cost_statistic_id:
        cost_meta = StatisticMetaData(
            has_mean=False,
            has_sum=True,
            name="Oma Helen cost",
            source=STATS_SOURCE,
            statistic_id=cost_statistic_id,
            unit_of_measurement=hass.config.currency or "EUR",
        )

    consumption_data: list[StatisticData] = []
    cost_data: list[StatisticData] | None = [] if cost_meta else None

    sum_kwh = last_sum_kwh
    sum_cost = last_sum_cost
    last_price_eur_per_kwh = None
    last_interval_start = None

    for point in points:
        sum_kwh += point.consumption_kwh
        consumption_data.append(StatisticData(start=point.start, state=point.consumption_kwh, sum=sum_kwh))

        spot_eur_per_kwh = _spot_to_eur_per_kwh(point.spot_price_c_per_kwh)
        if spot_eur_per_kwh is not None:
            last_price_eur_per_kwh = spot_eur_per_kwh

        if cost_data is not None and spot_eur_per_kwh is not None:
            sum_cost += point.consumption_kwh * spot_eur_per_kwh
            cost_data.append(
                StatisticData(
                    start=point.start,
                    state=point.consumption_kwh * spot_eur_per_kwh,
                    sum=sum_cost,
                )
            )

        last_interval_start = point.start

    return (
        (consumption_meta, consumption_data),
        (cost_meta, cost_data) if cost_meta and cost_data is not None else None,
        _LastValues(
            last_interval_start=last_interval_start,
            last_spot_price_eur_per_kwh=last_price_eur_per_kwh,
            last_sum_kwh=sum_kwh,
            last_sum_cost=sum_cost,
        ),
    )


async def insert_statistics(
    hass: HomeAssistant,
    consumption_stats,
    cost_stats,
    *,
    force_overwrite: bool,
) -> None:
    from homeassistant.components.recorder.statistics import async_add_external_statistics

    consumption_meta, consumption_data = consumption_stats
    await async_add_external_statistics(hass, consumption_meta, consumption_data)

    if cost_stats:
        cost_meta, cost_data = cost_stats
        if cost_meta is not None:
            await async_add_external_statistics(hass, cost_meta, cost_data)
