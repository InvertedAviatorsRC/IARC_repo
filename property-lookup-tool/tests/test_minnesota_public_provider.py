from property_lookup.models import PropertyData
from property_lookup.providers.mn.minnesota_public_provider import (
    MinnesotaPublicProvider,
)


class FakeResponse:
    def __init__(self, county):
        self.county = county

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "result": {
                "addressMatches": [
                    {
                        "matchedAddress": "12649 MONTEREY AVE S, SAVAGE, MN, 55378",
                        "addressComponents": {"state": "MN"},
                        "coordinates": {"x": -93.33689, "y": 44.77402},
                        "geographies": {
                            "Counties": [{"NAME": self.county, "GEOID": "27139"}]
                        },
                    }
                ]
            }
        }


class GeocoderSession:
    def __init__(self, county="Scott County"):
        self.county = county

    def get(self, url, **kwargs):
        return FakeResponse(self.county)


class StubBroadProvider:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def lookup_property(self, address, latitude, longitude, county):
        self.calls.append((address, latitude, longitude, county))
        return self.result


class ScottDetailProvider:
    def lookup_property(self, address):
        return PropertyData(
            input_address=address,
            normalized_address=address,
            state="MN",
            county="Scott County",
            parcel_id="260020210",
            beds=3,
            baths=1,
            source="Scott County public parcel data",
            source_url="https://example.gov/scott",
        ).refresh_unavailable_fields()


class StubRegistry:
    def __init__(self, provider):
        self.provider = provider
        self.requested_county = None

    def get_provider(self, county, session=None):
        self.requested_county = county
        return self.provider


def test_minnesota_public_provider_routes_scott_county_address():
    statewide_result = PropertyData(
        input_address="address",
        normalized_address="address",
        state="MN",
        county="Scott County",
        parcel_id="260020210",
        assessed_land_value=120700,
        assessed_building_value=169300,
        tax_assessed_value=290000,
        annual_property_tax=3738,
        source="Minnesota Geospatial Commons public parcel data",
        source_url="https://example.gov/mngeo",
    )
    statewide = StubBroadProvider(statewide_result)
    registry = StubRegistry(ScottDetailProvider())
    provider = MinnesotaPublicProvider(
        session=GeocoderSession(),
        statewide_provider=statewide,
        metrogis_provider=StubBroadProvider(None),
        county_registry=registry,
    )

    result = provider.lookup_property(
        "12649 Monterey Ave S, Savage, MN 55378"
    )

    assert registry.requested_county == "Scott County"
    assert result.parcel_id == "260020210"
    assert result.beds == 3
    assert result.baths == 1
    assert result.annual_property_tax == 3738
    assert "Scott County public parcel data" in result.source
    assert statewide.calls[0][3] == "Scott County"


def test_unsupported_minnesota_county_returns_graceful_partial_result():
    provider = MinnesotaPublicProvider(
        session=GeocoderSession("Koochiching County"),
        statewide_provider=StubBroadProvider(None),
        metrogis_provider=StubBroadProvider(None),
        county_registry=StubRegistry(None),
    )

    result = provider.lookup_property(
        "100 Main St, International Falls, MN 56649"
    )

    assert result.state == "MN"
    assert result.county == "Koochiching County"
    assert result.parcel_id is None
    assert "not implemented yet" in result.raw_data["coverage_message"]
    assert "parcel_id" in result.unavailable_fields
