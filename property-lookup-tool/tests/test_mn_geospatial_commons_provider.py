from property_lookup.providers.mn.mn_geospatial_commons_provider import (
    MNGeospatialCommonsProvider,
)


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "features": [
                {
                    "attributes": {
                        "county_pin": "wrong-neighbor",
                        "anumber": 12641,
                        "st_name": "Monterey",
                        "st_pos_typ": "Avenue",
                        "st_pos_dir": "South",
                        "zip": "55378",
                    }
                },
                {
                    "attributes": {
                        "county_pin": "260020210",
                        "anumber": 12649,
                        "st_name": "Monterey",
                        "st_pos_typ": "Avenue",
                        "st_pos_dir": "South",
                        "zip": "55378",
                        "co_name": "Scott",
                        "acres_poly": 0.21,
                        "emv_land": 120700,
                        "emv_bldg": 169300,
                        "emv_total": 290000,
                        "total_tax": 3738,
                        "useclass1": "Residential Single Unit",
                        "fin_sq_ft": 1678,
                        "year_built": 1959,
                        "sale_date": 1347235200000,
                        "sale_value": 123750,
                    }
                },
            ]
        }


class FakeSession:
    def __init__(self):
        self.kwargs = None

    def get(self, url, **kwargs):
        self.kwargs = kwargs
        return FakeResponse()


def test_mngeo_provider_selects_exact_address_and_maps_standard_fields():
    session = FakeSession()
    result = MNGeospatialCommonsProvider(session=session).lookup_property(
        "12649 Monterey Ave S, Savage, MN 55378",
        latitude=44.77402,
        longitude=-93.33689,
        county="Scott County",
    )

    assert result is not None
    assert result.parcel_id == "260020210"
    assert result.assessed_land_value == 120700
    assert result.assessed_building_value == 169300
    assert result.tax_assessed_value == 290000
    assert result.annual_property_tax == 3738
    assert result.square_feet == 1678
    assert result.last_sold_date == "2012-09-10"
    assert result.estimated_market_value is None
    assert session.kwargs["params"]["distance"] == "125"
    assert "owner_name" not in session.kwargs["params"]["outFields"]
