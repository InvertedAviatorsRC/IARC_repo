"""Router for free Minnesota address, statewide, regional, and county data."""

from dataclasses import dataclass
from typing import Any

import requests

from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider, ProviderError
from property_lookup.providers.mn.county_provider_registry import (
    CountyProviderRegistry,
)
from property_lookup.providers.mn.metrogis_provider import MetroGISProvider
from property_lookup.providers.mn.mn_geospatial_commons_provider import (
    MNGeospatialCommonsProvider,
)
from property_lookup.services.address_normalizer import normalize_address


@dataclass(frozen=True, slots=True)
class MinnesotaLocation:
    normalized_address: str
    state: str
    county: str
    latitude: float
    longitude: float
    raw_data: dict[str, Any]


class MinnesotaPublicProvider(PropertyProvider):
    """Resolve a Minnesota address and route through free public parcel sources."""

    GEOCODER_URL = (
        "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
    )
    GEOCODER_SOURCE = "U.S. Census Geocoder"

    def __init__(
        self,
        session: requests.Session | None = None,
        statewide_provider: MNGeospatialCommonsProvider | None = None,
        metrogis_provider: MetroGISProvider | None = None,
        county_registry: CountyProviderRegistry | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.session = session or requests.Session()
        self.statewide_provider = statewide_provider or MNGeospatialCommonsProvider(
            session=self.session
        )
        self.metrogis_provider = metrogis_provider or MetroGISProvider(
            session=self.session
        )
        self.county_registry = county_registry or CountyProviderRegistry()
        self.timeout = timeout

    def lookup_property(self, address: str) -> PropertyData:
        normalized_input = normalize_address(address)
        location = self._geocode(normalized_input)
        if location.state != "MN":
            raise ProviderError(
                "MinnesotaPublicProvider only supports addresses located in Minnesota."
            )

        provider_errors: list[str] = []
        result = self._try_broad_provider(
            self.statewide_provider,
            "Minnesota Geospatial Commons",
            normalized_input,
            location,
            provider_errors,
        )
        if result is None:
            result = self._try_broad_provider(
                self.metrogis_provider,
                "MetroGIS",
                normalized_input,
                location,
                provider_errors,
            )

        county_provider = self.county_registry.get_provider(
            location.county, session=self.session
        )
        county_result: PropertyData | None = None
        if county_provider is not None:
            try:
                county_result = county_provider.lookup_property(normalized_input)
            except (ProviderError, NotImplementedError) as exc:
                provider_errors.append(f"{location.county} provider: {exc}")

        if result is None and county_result is not None:
            result = county_result
        elif result is not None and county_result is not None:
            result = _merge_public_results(result, county_result)

        if result is None:
            result = PropertyData(
                input_address=address,
                normalized_address=location.normalized_address,
                state="MN",
                county=location.county,
                source=f"Minnesota public lookup via {self.GEOCODER_SOURCE}",
                source_url=self.GEOCODER_URL,
            )

        result.input_address = address
        result.normalized_address = location.normalized_address
        result.state = "MN"
        result.county = location.county
        result.raw_data["geocoder"] = location.raw_data
        result.raw_data["provider_errors"] = provider_errors

        if county_provider is None:
            if result.parcel_id:
                coverage_message = (
                    f"{location.county} county-specific enrichment is not implemented "
                    "yet; available statewide/regional public parcel fields are shown."
                )
            else:
                coverage_message = (
                    "No matching parcel was found in the broad public datasets, and "
                    f"{location.county} county-specific lookup is not implemented yet. "
                    "The verified address and county are shown."
                )
            result.raw_data["coverage_message"] = coverage_message
        elif provider_errors:
            result.raw_data["coverage_message"] = (
                "One or more public sources were unavailable; all fields successfully "
                "retrieved from the remaining sources are shown."
            )

        return result.refresh_unavailable_fields()

    def _try_broad_provider(
        self,
        provider: Any,
        label: str,
        address: str,
        location: MinnesotaLocation,
        errors: list[str],
    ) -> PropertyData | None:
        try:
            return provider.lookup_property(
                address,
                location.latitude,
                location.longitude,
                location.county,
            )
        except ProviderError as exc:
            errors.append(f"{label}: {exc}")
            return None

    def _geocode(self, address: str) -> MinnesotaLocation:
        try:
            response = self.session.get(
                self.GEOCODER_URL,
                params={
                    "address": address,
                    "benchmark": "Public_AR_Current",
                    "vintage": "Current_Current",
                    "format": "json",
                },
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.Timeout as exc:
            raise ProviderError("The public Census address geocoder timed out.") from exc
        except requests.RequestException as exc:
            raise ProviderError(
                f"Could not connect to the public Census address geocoder: {exc}"
            ) from exc
        except ValueError as exc:
            raise ProviderError("The public Census geocoder returned invalid JSON.") from exc

        try:
            matches = payload["result"]["addressMatches"]
            match = matches[0]
            components = match["addressComponents"]
            coordinates = match["coordinates"]
            counties = match["geographies"]["Counties"]
            county = counties[0].get("NAME") or counties[0]["BASENAME"]
            state = components["state"].upper()
            latitude = float(coordinates["y"])
            longitude = float(coordinates["x"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ProviderError(
                "The public Census geocoder could not match that address. Check the "
                "street, city, state, and ZIP code."
            ) from exc

        return MinnesotaLocation(
            normalized_address=address,
            state=state,
            county=_county_name(str(county)),
            latitude=latitude,
            longitude=longitude,
            raw_data={
                "matched_address": match.get("matchedAddress"),
                "coordinates": coordinates,
                "county": counties[0],
                "source_name": self.GEOCODER_SOURCE,
                "source_url": self.GEOCODER_URL,
            },
        )


def _merge_public_results(
    primary: PropertyData, county_detail: PropertyData
) -> PropertyData:
    fields = (
        "parcel_id",
        "property_type",
        "year_built",
        "beds",
        "baths",
        "square_feet",
        "lot_size",
        "assessed_land_value",
        "assessed_building_value",
        "tax_assessed_value",
        "annual_property_tax",
        "last_sold_date",
        "last_sold_price",
        "estimated_market_value",
        "list_price",
    )
    for field_name in fields:
        if getattr(primary, field_name) is None:
            setattr(primary, field_name, getattr(county_detail, field_name))

    primary.source = f"{primary.source}; {county_detail.source}"
    primary.raw_data["county_enrichment"] = county_detail.raw_data
    primary.raw_data["additional_source"] = {
        "name": county_detail.source,
        "url": county_detail.source_url,
    }
    return primary


def _county_name(value: str) -> str:
    value = value.strip()
    return value if value.lower().endswith(" county") else f"{value} County"
