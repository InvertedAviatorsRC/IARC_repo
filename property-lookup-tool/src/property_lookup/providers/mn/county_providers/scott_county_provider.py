"""Scott County enrichment through its official public ArcGIS parcel layer."""

import re
from typing import Any

import requests

from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider, ProviderError
from property_lookup.providers.mn.mn_geospatial_commons_provider import (
    canonical_street,
    number,
    text,
    zip_code,
)
from property_lookup.services.address_normalizer import normalize_address


class ScottCountyProvider(PropertyProvider):
    LAYER_URL = (
        "https://gis.co.scott.mn.us/arcgis/rest/services/AGOL/"
        "SC_PARCELS_AGOL_WM/MapServer/0"
    )
    SOURCE_NAME = "Scott County MN public parcel data"
    OUT_FIELDS = ",".join(
        (
            "PID",
            "PropertyAddress1",
            "PropertyCity",
            "PropertyZip",
            "Classification",
            "ModelDesc",
            "NumBathRooms",
            "NumBedrooms",
            "YearBuilt",
            "AGLASqFt",
            "GISAcres",
            "DeededAcres",
            "AssessmentYear",
            "EMVLand",
            "EMVImprove",
            "EMVTotal",
            "NextAssessmentYear",
            "NextEMVLand",
            "NextEMVImprove",
            "NextEMVTotal",
            "LastSaleDate",
            "LastSalePrice",
        )
    )

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def lookup_property(self, address: str) -> PropertyData:
        normalized = normalize_address(address)
        if not re.search(r"\b(?:MN|MINNESOTA)\b", normalized, re.IGNORECASE):
            raise ProviderError(
                "Scott County provider only supports Minnesota property addresses."
            )
        house_number = _house_number(normalized)
        target_street = canonical_street(normalized.split(",", 1)[0])
        target_zip = zip_code(normalized)
        payload = self._query(house_number)

        features = payload.get("features")
        if not isinstance(features, list):
            raise ProviderError("Scott County returned an unexpected parcel response.")

        for feature in features:
            if not isinstance(feature, dict) or not isinstance(
                feature.get("attributes"), dict
            ):
                continue
            attributes = feature["attributes"]
            candidate = canonical_street(
                str(attributes.get("PropertyAddress1") or "")
            )
            candidate_zip = text(attributes.get("PropertyZip"))
            if candidate == target_street and (
                not target_zip or not candidate_zip or target_zip == candidate_zip
            ):
                return self._map_record(address, attributes)

        raise ProviderError("Scott County found no matching parcel for the address.")

    def _query(self, house_number: int) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.LAYER_URL}/query",
                params={
                    "where": f"PropertyHouseNo={house_number}",
                    "outFields": self.OUT_FIELDS,
                    "returnGeometry": "false",
                    "f": "json",
                },
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise ProviderError("Scott County's public GIS service timed out.") from exc
        except requests.RequestException as exc:
            raise ProviderError(
                f"Could not connect to Scott County's public GIS service: {exc}"
            ) from exc
        except ValueError as exc:
            raise ProviderError("Scott County returned invalid JSON.") from exc

        if not isinstance(payload, dict):
            raise ProviderError("Scott County returned an unexpected parcel response.")
        if "error" in payload:
            error = payload.get("error")
            detail = error.get("message") if isinstance(error, dict) else error
            raise ProviderError(f"Scott County GIS reported an error: {detail}")
        return payload

    def _map_record(
        self, address: str, attributes: dict[str, Any]
    ) -> PropertyData:
        use_next = (_integer(attributes.get("NextAssessmentYear")) or 0) >= (
            _integer(attributes.get("AssessmentYear")) or 0
        )
        prefix = "Next" if use_next else ""
        acres = number(attributes.get("GISAcres"))
        if acres is None:
            acres = number(attributes.get("DeededAcres"))

        result = PropertyData(
            input_address=address,
            normalized_address=_format_address(attributes, address),
            state="MN",
            county="Scott County",
            parcel_id=text(attributes.get("PID")),
            property_type=text(attributes.get("ModelDesc"))
            or text(attributes.get("Classification")),
            year_built=_integer(attributes.get("YearBuilt")),
            beds=number(attributes.get("NumBedrooms")),
            baths=number(attributes.get("NumBathRooms")),
            square_feet=number(attributes.get("AGLASqFt")),
            lot_size=acres * 43_560 if acres is not None else None,
            assessed_land_value=number(attributes.get(f"{prefix}EMVLand")),
            assessed_building_value=number(attributes.get(f"{prefix}EMVImprove")),
            tax_assessed_value=number(attributes.get(f"{prefix}EMVTotal")),
            last_sold_date=text(attributes.get("LastSaleDate")),
            last_sold_price=number(attributes.get("LastSalePrice")),
            source=self.SOURCE_NAME,
            source_url=self.LAYER_URL,
            raw_data={"county_parcel_attributes": attributes},
        )
        return result.refresh_unavailable_fields()


def _house_number(address: str) -> int:
    match = re.match(r"\s*(\d+)", address)
    if not match:
        raise ProviderError("Address must begin with a numeric house number.")
    return int(match.group(1))


def _integer(value: Any) -> int | None:
    parsed = number(value)
    return int(parsed) if parsed is not None and parsed > 0 else None


def _format_address(attributes: dict[str, Any], fallback: str) -> str:
    street = text(attributes.get("PropertyAddress1"))
    city = text(attributes.get("PropertyCity"))
    postal_code = text(attributes.get("PropertyZip"))
    if not street or not city:
        return normalize_address(fallback)
    return f"{street.title()}, {city.title()}, MN {postal_code}".strip()
