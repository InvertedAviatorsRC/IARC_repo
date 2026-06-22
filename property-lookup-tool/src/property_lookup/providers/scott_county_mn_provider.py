"""Free property lookup using Scott County, Minnesota's public parcel GIS layer."""

import re
from typing import Any

import requests

from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider, ProviderError
from property_lookup.services.address_normalizer import normalize_address


class ScottCountyMNProvider(PropertyProvider):
    """Query Scott County's official, public ArcGIS parcel service by address."""

    LAYER_URL = (
        "https://gis.co.scott.mn.us/arcgis/rest/services/AGOL/"
        "SC_PARCELS_AGOL_WM/MapServer/0"
    )
    QUERY_URL = f"{LAYER_URL}/query"
    OPEN_DATA_URL = "https://www.scottcountymn.gov/308/Geographic-Information-Systems-GIS"
    SOURCE_NAME = "Scott County MN public parcel data"
    OUT_FIELDS = ",".join(
        (
            "PID",
            "PropertyAddress1",
            "PropertyAddress2",
            "PropertyCity",
            "PropertyZip",
            "Classification",
            "ModelDesc",
            "ArchitectureDesc",
            "NumBathRooms",
            "NumBedrooms",
            "YearBuilt",
            "AGLASqFt",
            "BasementFinishedSqft",
            "GISAcres",
            "DeededAcres",
            "AssessmentYear",
            "EMVTotal",
            "NextAssessmentYear",
            "NextEMVTotal",
            "LastSaleDate",
            "LastSalePrice",
            "TaxYear",
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
        normalized_input = normalize_address(address)
        self._validate_minnesota_address(normalized_input)
        house_number = _house_number(normalized_input)
        requested_street = _street_line(normalized_input)
        requested_zip = _zip_code(normalized_input)

        payload = self._query(house_number)
        features = payload.get("features")
        if not isinstance(features, list):
            raise ProviderError("Scott County returned an unexpected parcel response.")

        attributes = _find_address_match(features, requested_street, requested_zip)
        if attributes is None:
            raise ProviderError(
                "Scott County public parcel data found no matching address. Check the "
                "address, or select another provider for property outside Scott County, MN."
            )

        acres = _number(attributes.get("GISAcres"))
        if acres is None:
            acres = _number(attributes.get("DeededAcres"))

        assessed_value = _latest_assessed_value(attributes)
        property_type = attributes.get("ModelDesc") or attributes.get("Classification")

        return PropertyData(
            input_address=address,
            normalized_address=_format_county_address(attributes, normalized_input),
            parcel_id=_text(attributes.get("PID")),
            year_built=_integer(attributes.get("YearBuilt")),
            # County records do not provide Zestimate-style or active-listing values.
            list_price=None,
            estimated_value=None,
            rent_estimate=None,
            beds=_number(attributes.get("NumBedrooms")),
            baths=_number(attributes.get("NumBathRooms")),
            square_feet=_number(attributes.get("AGLASqFt")),
            lot_size=acres * 43_560 if acres is not None else None,
            property_type=_text(property_type),
            last_sold_date=_text(attributes.get("LastSaleDate")),
            last_sold_price=_number(attributes.get("LastSalePrice")),
            tax_assessed_value=assessed_value,
            # The open parcel layer exposes tax year, but not the actual tax bill.
            annual_property_tax=None,
            source=self.SOURCE_NAME,
            source_urls=[self.LAYER_URL, self.OPEN_DATA_URL],
            raw_data={
                "arcgis_attributes": attributes,
                "source_name": self.SOURCE_NAME,
                "source_url": self.LAYER_URL,
            },
        )

    def _query(self, house_number: int) -> dict[str, Any]:
        try:
            response = self.session.get(
                self.QUERY_URL,
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
            raise ProviderError(
                "Scott County's public GIS service timed out. Please try again."
            ) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            raise ProviderError(
                f"Scott County's public GIS request failed (HTTP {status})."
            ) from exc
        except requests.RequestException as exc:
            raise ProviderError(
                f"Could not connect to Scott County's public GIS service: {exc}"
            ) from exc
        except ValueError as exc:
            raise ProviderError(
                "Scott County's public GIS service returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ProviderError("Scott County returned an unexpected parcel response.")
        if "error" in payload:
            error = payload.get("error")
            detail = error.get("message") if isinstance(error, dict) else error
            raise ProviderError(f"Scott County GIS reported an error: {detail}")
        return payload

    @staticmethod
    def _validate_minnesota_address(address: str) -> None:
        if not re.search(r"\b(?:MN|MINNESOTA)\b", address, re.IGNORECASE):
            raise ProviderError(
                "ScottCountyMNProvider only supports addresses in Scott County, Minnesota."
            )


def _house_number(address: str) -> int:
    match = re.match(r"\s*(\d+)", address)
    if not match:
        raise ProviderError("Address must begin with a numeric house number.")
    return int(match.group(1))


def _street_line(address: str) -> str:
    return address.split(",", 1)[0]


def _zip_code(address: str) -> str | None:
    locality = address.split(",", 1)[1] if "," in address else ""
    match = re.search(r"\b(\d{5})(?:-\d{4})?\b", locality)
    return match.group(1) if match else None


def _find_address_match(
    features: list[Any], requested_street: str, requested_zip: str | None
) -> dict[str, Any] | None:
    wanted = _canonical_street(requested_street)
    for feature in features:
        if not isinstance(feature, dict) or not isinstance(feature.get("attributes"), dict):
            continue
        attributes = feature["attributes"]
        candidate = _canonical_street(str(attributes.get("PropertyAddress1") or ""))
        candidate_zip = _text(attributes.get("PropertyZip"))
        if candidate == wanted and (not requested_zip or candidate_zip == requested_zip):
            return attributes
    return None


def _canonical_street(value: str) -> str:
    replacements = {
        "NORTH": "N",
        "SOUTH": "S",
        "EAST": "E",
        "WEST": "W",
        "AVENUE": "AVE",
        "STREET": "ST",
        "ROAD": "RD",
        "DRIVE": "DR",
        "BOULEVARD": "BLVD",
        "LANE": "LN",
        "COURT": "CT",
        "TRAIL": "TRL",
        "PARKWAY": "PKWY",
    }
    tokens = re.sub(r"[^A-Z0-9 ]", " ", value.upper()).split()
    return " ".join(replacements.get(token, token) for token in tokens)


def _latest_assessed_value(attributes: dict[str, Any]) -> float | None:
    current_year = _integer(attributes.get("AssessmentYear")) or 0
    next_year = _integer(attributes.get("NextAssessmentYear")) or 0
    if next_year >= current_year:
        next_value = _number(attributes.get("NextEMVTotal"))
        if next_value is not None:
            return next_value
    return _number(attributes.get("EMVTotal"))


def _format_county_address(attributes: dict[str, Any], fallback: str) -> str:
    street = _text(attributes.get("PropertyAddress1"))
    city = _text(attributes.get("PropertyCity"))
    zip_code = _text(attributes.get("PropertyZip"))
    if not street or not city:
        return fallback
    street = street.title()
    return f"{street}, {city.title()}, MN {zip_code}".strip()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None
