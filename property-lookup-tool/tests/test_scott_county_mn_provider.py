import pytest

from property_lookup.providers.base import ProviderError
from property_lookup.providers.scott_county_mn_provider import ScottCountyMNProvider


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "features": [
                {
                    "attributes": {
                        "PID": "260020210",
                        "PropertyAddress1": "12649 MONTEREY AVE S",
                        "PropertyCity": "Savage",
                        "PropertyZip": "55378",
                        "Classification": "201 1A/4BB(1) RESIDENTIAL SINGLE UNIT",
                        "ModelDesc": "Single-Family",
                        "ArchitectureDesc": "Rambler",
                        "NumBathRooms": 1.0,
                        "NumBedrooms": 3.0,
                        "YearBuilt": 1959,
                        "AGLASqFt": 1078,
                        "GISAcres": 0.20638886,
                        "AssessmentYear": 2025,
                        "EMVTotal": 290100,
                        "NextAssessmentYear": 2026,
                        "NextEMVTotal": 290000,
                        "LastSaleDate": "09/10/2012",
                        "LastSalePrice": 123750,
                        "TaxYear": 2026,
                    }
                }
            ]
        }


class FakeSession:
    def __init__(self):
        self.call = None

    def get(self, url, **kwargs):
        self.call = (url, kwargs)
        return FakeResponse()


def test_scott_county_provider_maps_real_public_fields():
    session = FakeSession()
    result = ScottCountyMNProvider(session=session).lookup_property(
        "12649 Monterey Avenue South, Savage, MN 55378"
    )

    assert result.parcel_id == "260020210"
    assert result.normalized_address == "12649 Monterey Ave S, Savage, MN 55378"
    assert result.property_type == "Single-Family"
    assert result.year_built == 1959
    assert result.beds == 3
    assert result.baths == 1
    assert result.square_feet == 1078
    assert round(result.lot_size) == 8990
    assert result.tax_assessed_value == 290000
    assert result.estimated_value is None
    assert result.list_price is None
    assert result.annual_property_tax is None
    assert result.source_urls
    assert session.call[1]["params"]["where"] == "PropertyHouseNo=12649"
    assert "TaxPayerName" not in session.call[1]["params"]["outFields"]


def test_scott_county_provider_rejects_non_minnesota_address_without_request():
    session = FakeSession()

    with pytest.raises(ProviderError, match="Scott County"):
        ScottCountyMNProvider(session=session).lookup_property(
            "123 Main St, Philadelphia, PA 19103"
        )

    assert session.call is None
