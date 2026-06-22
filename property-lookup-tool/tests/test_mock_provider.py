from property_lookup.providers.mock_provider import MockProvider


def test_mock_provider_returns_expected_data():
    result = MockProvider().lookup_property(" 123 Main St,  Philadelphia, PA ")

    assert result.input_address == " 123 Main St,  Philadelphia, PA "
    assert result.normalized_address == "123 Main St, Philadelphia, PA"
    assert result.estimated_market_value == 325_000
    assert result.source == "Mock (sample data)"
    assert result.raw_data == {"mock": True}
