"""Statewide opt-in parcel lookup through Minnesota Geospatial Commons."""

import re
from datetime import datetime, timezone
from typing import Any

import requests

from property_lookup.models import PropertyData
from property_lookup.providers.base import ProviderError
from property_lookup.services.address_normalizer import normalize_address


class MNGeospatialCommonsProvider:
    """Query MnGeo's standardized, public statewide parcel FeatureServer."""

    LAYER_URL = (
        "https://enterprise.gisdata.mn.gov/aghost/rest/services/"
        "us_mn_state_mngeo/plan_parcels_open/FeatureServer/1"
    )
    SOURCE_NAME = "Minnesota Geospatial Commons public parcel data"
    OUT_FIELDS = ",".join(
        (
            "county_pin",
            "state_pin",
            "anumberpre",
            "anumber",
            "anumbersuf",
            "st_pre_dir",
            "st_name",
            "st_pos_typ",
            "st_pos_dir",
            "zip",
            "postcomm",
            "co_name",
            "acres_poly",
            "acres_deed",
            "emv_land",
            "emv_bldg",
            "emv_total",
            "total_tax",
            "useclass1",
            "dwell_type",
            "home_style",
            "fin_sq_ft",
            "year_built",
            "sale_date",
            "sale_value",
        )
    )

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 25.0,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout

    def lookup_property(
        self,
        address: str,
        latitude: float,
        longitude: float,
        county: str,
    ) -> PropertyData | None:
        payload = self._query(latitude, longitude)
        features = payload.get("features")
        if not isinstance(features, list):
            raise ProviderError("MnGeo returned an unexpected parcel response.")

        target = canonical_street(address.split(",", 1)[0])
        target_zip = zip_code(address)
        for feature in features:
            if not isinstance(feature, dict) or not isinstance(
                feature.get("attributes"), dict
            ):
                continue
            attributes = _lower_keys(feature["attributes"])
            if _candidate_street(attributes) != target:
                continue
            candidate_zip = text(attributes.get("zip"))
            if target_zip and candidate_zip and target_zip != candidate_zip:
                continue
            return self._map_record(address, county, attributes)
        return None

    def _query(self, latitude: float, longitude: float) -> dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.LAYER_URL}/query",
                params={
                    "geometry": f"{longitude},{latitude}",
                    "geometryType": "esriGeometryPoint",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "distance": "125",
                    "units": "esriSRUnit_Meter",
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
            raise ProviderError("Minnesota's statewide parcel service timed out.") from exc
        except requests.RequestException as exc:
            raise ProviderError(
                f"Could not connect to Minnesota's statewide parcel service: {exc}"
            ) from exc
        except ValueError as exc:
            raise ProviderError(
                "Minnesota's statewide parcel service returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ProviderError("MnGeo returned an unexpected parcel response.")
        if "error" in payload:
            error = payload.get("error")
            detail = error.get("message") if isinstance(error, dict) else error
            raise ProviderError(f"MnGeo parcel service reported an error: {detail}")
        return payload

    def _map_record(
        self, address: str, county: str, attributes: dict[str, Any]
    ) -> PropertyData:
        acres = number(attributes.get("acres_poly"))
        if acres is None:
            acres = number(attributes.get("acres_deed"))

        property_type = text(attributes.get("dwell_type")) or text(
            attributes.get("useclass1")
        )
        result = PropertyData(
            input_address=address,
            normalized_address=normalize_address(address),
            state="MN",
            county=_county_name(county),
            parcel_id=text(attributes.get("county_pin"))
            or text(attributes.get("state_pin")),
            property_type=property_type,
            year_built=integer_or_none(attributes.get("year_built")),
            square_feet=positive_number(attributes.get("fin_sq_ft")),
            lot_size=acres * 43_560 if acres is not None else None,
            assessed_land_value=number(attributes.get("emv_land")),
            assessed_building_value=number(attributes.get("emv_bldg")),
            tax_assessed_value=number(attributes.get("emv_total")),
            annual_property_tax=number(attributes.get("total_tax")),
            last_sold_date=arcgis_date(attributes.get("sale_date")),
            last_sold_price=positive_number(attributes.get("sale_value")),
            estimated_market_value=None,
            list_price=None,
            source=self.SOURCE_NAME,
            source_url=self.LAYER_URL,
            raw_data={
                "statewide_parcel_attributes": attributes,
                "source_name": self.SOURCE_NAME,
                "source_url": self.LAYER_URL,
            },
        )
        return result.refresh_unavailable_fields()


def canonical_street(value: str) -> str:
    replacements = {
        "NORTH": "N",
        "SOUTH": "S",
        "EAST": "E",
        "WEST": "W",
        "NORTHEAST": "NE",
        "NORTHWEST": "NW",
        "SOUTHEAST": "SE",
        "SOUTHWEST": "SW",
        "AVENUE": "AVE",
        "STREET": "ST",
        "ROAD": "RD",
        "DRIVE": "DR",
        "BOULEVARD": "BLVD",
        "LANE": "LN",
        "COURT": "CT",
        "TRAIL": "TRL",
        "PARKWAY": "PKWY",
        "HIGHWAY": "HWY",
    }
    tokens = re.sub(r"[^A-Z0-9 ]", " ", value.upper()).split()
    return " ".join(replacements.get(token, token) for token in tokens)


def zip_code(address: str) -> str | None:
    locality = address.split(",", 1)[1] if "," in address else ""
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", locality)
    return match.group(1) if match else None


def text(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def positive_number(value: Any) -> float | None:
    parsed = number(value)
    return parsed if parsed is not None and parsed > 0 else None


def integer_or_none(value: Any) -> int | None:
    parsed = positive_number(value)
    return int(parsed) if parsed is not None else None


def arcgis_date(value: Any) -> str | None:
    milliseconds = positive_number(value)
    if milliseconds is None:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).date().isoformat()


def _candidate_street(attributes: dict[str, Any]) -> str:
    parts = (
        attributes.get("anumberpre"),
        attributes.get("anumber"),
        attributes.get("anumbersuf"),
        attributes.get("st_pre_dir"),
        attributes.get("st_name"),
        attributes.get("st_pos_typ"),
        attributes.get("st_pos_dir"),
    )
    return canonical_street(" ".join(str(part) for part in parts if text(part)))


def _lower_keys(attributes: dict[str, Any]) -> dict[str, Any]:
    return {str(key).lower(): value for key, value in attributes.items()}


def _county_name(county: str) -> str:
    county = county.strip()
    return county if county.lower().endswith(" county") else f"{county} County"
