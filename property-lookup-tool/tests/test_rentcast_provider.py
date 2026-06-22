from property_lookup.providers.rentcast_provider import RentCastProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.responses = [
            FakeResponse(
                [
                    {
                        "formattedAddress": "5500 Grand Lake Dr, San Antonio, TX 78244",
                        "propertyType": "Single Family",
                        "bedrooms": 3,
                        "bathrooms": 2,
                        "squareFootage": 1878,
                        "lotSize": 8850,
                        "yearBuilt": 1973,
                        "lastSaleDate": "2024-11-18T00:00:00.000Z",
                        "lastSalePrice": 270000,
                        "taxAssessments": {"2025": {"value": 245000}},
                        "propertyTaxes": {"2025": {"total": 4700}},
                    }
                ]
            ),
            FakeResponse({"price": 300000, "comparables": []}),
        ]

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def test_rentcast_provider_combines_records_and_valuation():
    session = FakeSession()
    result = RentCastProvider("secret", session=session).lookup_property(
        "5500 Grand Lake Dr, San Antonio, TX 78244"
    )

    assert result.estimated_market_value == 300000
    assert result.tax_assessed_value == 245000
    assert result.annual_property_tax == 4700
    assert result.last_sold_date == "2024-11-18"
    assert len(session.calls) == 2
    assert session.calls[0][1]["headers"]["X-Api-Key"] == "secret"
    assert "property_record" in result.raw_data
    assert "value_estimate" in result.raw_data
