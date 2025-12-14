from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from helenservice.api_client import HelenApiClient
from helenservice.api_exceptions import HelenAuthenticationException, InvalidDeliverySiteException
from helenservice.api_response import MeasurementsWithSpotPriceResponse


class OmaHelenAuthError(Exception):
    pass


class OmaHelenDeliverySiteError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class OmaHelenLoginResult:
    access_token: str
    delivery_site_ids: list[str]


class _TokenSession:
    def __init__(self, access_token: str) -> None:
        self._access_token = access_token

    def get_access_token(self) -> str:
        return self._access_token

    def close(self) -> None:
        return None


def login(username: str, password: str) -> OmaHelenLoginResult:
    try:
        client = HelenApiClient().login_and_init(username, password)
        token = client.get_api_access_token()
        delivery_site_ids = client.get_all_delivery_site_ids()
        return OmaHelenLoginResult(access_token=token, delivery_site_ids=delivery_site_ids)
    except HelenAuthenticationException as exc:
        raise OmaHelenAuthError from exc


def build_client(access_token: str, delivery_site_id: str | None) -> HelenApiClient:
    client = HelenApiClient()
    client._session = _TokenSession(access_token)  # type: ignore[attr-defined]
    client._latest_login_time = None  # type: ignore[attr-defined]
    client._refresh_api_client_state()  # type: ignore[attr-defined]

    if delivery_site_id:
        try:
            client.select_delivery_site_if_valid_id(delivery_site_id)
        except InvalidDeliverySiteException as exc:
            raise OmaHelenDeliverySiteError from exc

    return client


def get_measurements_with_spot_prices(
    client: HelenApiClient,
    start: date,
    end: date,
    resolution: str,
) -> MeasurementsWithSpotPriceResponse:
    return client.get_measurements_with_spot_prices(start, end, resolution)

