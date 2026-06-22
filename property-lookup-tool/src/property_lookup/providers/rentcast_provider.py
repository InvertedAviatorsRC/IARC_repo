"""Real RentCast API provider."""

from collections.abc import Mapping
from typing import Any

import requests

from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider, ProviderError
from property_lookup.services.address_normalizer import normalize_address


class RentCastProvider(PropertyProvider):
    """Look up property records and value estimates through RentCast."""

    BASE_URL = "https://api.rentcast.io/v1"

    def __init__(
        self,
        api_key: str,
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError(
                "RentCast requires RENTCAST_API_KEY. Copy .env.example to .env, "
                "add your key, and try again (or pass --mock)."
            )
        self.api_key = api_key.strip()
        self.session = session or requests.Session()
        self.timeout = timeout

    def lookup_property(self, address: str) -> PropertyData:
        normalized_input = normalize_address(address)
        records_payload = self._get("/properties", {"address": normalized_input, "limit": 1})

        if not isinstance(records_payload, list) or not records_payload:
            raise ProviderError(f"RentCast found no property record for: {normalized_input}")

        record = records_payload[0]
        if not isinstance(record, dict):
            raise ProviderError("RentCast returned an unexpected property-record response.")

        value_payload = self._get("/avm/value", {"address": normalized_input})
        if not isinstance(value_payload, dict):
            raise ProviderError("RentCast returned an unexpected value-estimate response.")

        tax_assessment = _latest_mapping(record.get("taxAssessments"))
        property_tax = _latest_mapping(record.get("propertyTaxes"))

        return PropertyData(
            input_address=address,
            normalized_address=record.get("formattedAddress") or normalized_input,
            year_built=_number(record.get("yearBuilt"), int),
            list_price=_current_list_price(record.get("history")),
            estimated_value=_number(value_payload.get("price")),
            beds=_number(record.get("bedrooms")),
            baths=_number(record.get("bathrooms")),
            square_feet=_number(record.get("squareFootage")),
            lot_size=_number(record.get("lotSize")),
            property_type=record.get("propertyType"),
            last_sold_date=_date_only(record.get("lastSaleDate")),
            last_sold_price=_number(record.get("lastSalePrice")),
            tax_assessed_value=_first_number(
                tax_assessment, "value", "total", "assessedValue"
            ),
            annual_property_tax=_first_number(
                property_tax, "total", "amount", "taxAmount"
            ),
            source="RentCast",
            raw_data={
                "property_record": record,
                "value_estimate": value_payload,
            },
        )

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        try:
            response = self.session.get(
                f"{self.BASE_URL}{path}",
                headers={"Accept": "application/json", "X-Api-Key": self.api_key},
                params=params,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.Timeout as exc:
            raise ProviderError("RentCast timed out. Please try the lookup again.") from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            detail = _error_detail(exc.response)
            if status in (401, 403):
                message = "RentCast rejected the API key. Check RENTCAST_API_KEY in .env."
            elif status == 429:
                message = "RentCast rate limit or monthly request limit reached."
            else:
                message = f"RentCast request failed (HTTP {status})."
            if detail:
                message = f"{message} Provider message: {detail}"
            raise ProviderError(message) from exc
        except requests.RequestException as exc:
            raise ProviderError(f"Could not connect to RentCast: {exc}") from exc
        except ValueError as exc:
            raise ProviderError("RentCast returned a response that was not valid JSON.") from exc


def _number(value: Any, converter: type = float) -> Any:
    if value is None or value == "":
        return None
    try:
        return converter(value)
    except (TypeError, ValueError):
        return None


def _first_number(mapping: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        number = _number(mapping.get(key))
        if number is not None:
            return number
    return None


def _latest_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not value:
        return {}
    mappings = [(str(key), item) for key, item in value.items() if isinstance(item, Mapping)]
    if not mappings:
        return value
    return max(mappings, key=lambda pair: pair[0])[1]


def _date_only(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value.split("T", 1)[0]


def _current_list_price(history: Any) -> float | None:
    """Return the newest active listing price when record history includes one."""
    if not isinstance(history, Mapping):
        return None
    for _, event in sorted(history.items(), key=lambda item: str(item[0]), reverse=True):
        if not isinstance(event, Mapping):
            continue
        event_name = str(event.get("event") or "").lower()
        if "listed" in event_name or "listing" in event_name:
            return _number(event.get("price"))
        if "removed" in event_name or "sold" in event_name:
            return None
    return None


def _error_detail(response: requests.Response | None) -> str | None:
    if response is None:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if isinstance(payload, Mapping):
        detail = payload.get("message") or payload.get("error")
        return str(detail)[:300] if detail else None
    return None
