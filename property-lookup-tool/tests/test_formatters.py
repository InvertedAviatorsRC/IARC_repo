from datetime import datetime, timezone

from property_lookup.models import PropertyData
from property_lookup.output.formatters import format_property_summary


def test_formatter_prints_readable_property_summary():
    data = PropertyData(
        input_address="123 Main St, Philadelphia, PA",
        normalized_address="123 Main St, Philadelphia, PA 19103",
        year_built=1952,
        square_feet=1450,
        estimated_value=325000,
        source="RentCast",
        lookup_timestamp=datetime(2026, 6, 22, 19, 30, tzinfo=timezone.utc),
    )

    output = format_property_summary(data)

    assert "Square Feet: 1,450" in output
    assert "Year Built: 1952" in output
    assert "Estimated Value: $325,000" in output
    assert "List Price: Not available" in output
    assert "Source: RentCast" in output
