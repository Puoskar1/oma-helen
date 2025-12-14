# Oma Helen Home Assistant integration (WIP)

Custom integration to import Oma Helen electricity consumption as 15‑minute statistics into Home Assistant.

## Install (manual)

- Copy `custom_components/oma_helen/` into your Home Assistant `config/custom_components/`.
- Restart Home Assistant.
- Add **Oma Helen** via **Settings → Devices & services → Add integration**.

## What it does today

- Imports quarter-hourly consumption into recorder statistics once per day (and backfills on first setup).
- Optionally imports a basic cost statistic (currently: spot price only).
- Exposes two small sensors:
  - `sensor.<...>_last_import_date`
  - `sensor.<...>_last_spot_price`

## Energy dashboard

After data is imported, add it in **Settings → Energy**:

- **Electricity grid** → **Consumption**: pick the statistic `oma_helen:<delivery_site_id>:consumption`
- **Cost**: pick `oma_helen:<delivery_site_id>:cost` (only if enabled in config flow)

## Services

- `oma_helen.refresh_statistics` with `start_date` / `end_date` (YYYY-MM-DD) to re-fetch and overwrite the stored statistics for that range.

