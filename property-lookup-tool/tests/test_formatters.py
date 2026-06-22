from datetime import datetime, timezone

from property_lookup.models import PropertyData
from property_lookup.output.formatters import format_property_summary


def test_formatter_prints_readable_property_summary():
    data = PropertyData(
        input_address="123 Main St, Philadelphia, PA",
        normalized_address="123 Main St, Philadelphia, PA 19103",
        year_built=1952,
        square_feet=1450,
        estimated_market_value=325000,
        source="RentCast",
        lookup_timestamp=datetime(2026, 6, 22, 19, 30, tzinfo=timezone.utc),
    )

    output = format_property_summary(data)

    assert "Square Feet: 1,450" in output
    assert "Year Built: 1952" in output
    assert "Estimated Market Value: $325,000" in output
    assert "List Price: Not available" in output
    assert "Source: RentCast" in output


def test_formatter_explains_free_market_data_gaps_and_prints_sources():
    data = PropertyData(
        input_address="12649 Monterey Ave S, Savage, MN 55378",
        normalized_address="12649 Monterey Ave S, Savage, MN 55378",
        state="MN",
        county="Scott County",
        parcel_id="260020210",
        source="Minnesota public parcel data",
        source_url="https://example.gov/arcgis/rest/services/parcels/0",
    )

    output = format_property_summary(data)

    assert "Parcel ID: 260020210" in output
    assert "Estimated Market Value: Not available from free public source" in output
    assert "List Price: Not available from free public source" in output
    assert "Beds: Not available from free public source" in output
    assert "Source URL: https://example.gov/arcgis/rest/services/parcels/0" in output
