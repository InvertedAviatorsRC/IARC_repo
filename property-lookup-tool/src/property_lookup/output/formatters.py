"""Human-readable terminal output."""

from datetime import datetime

from property_lookup.models import PropertyData


def format_property_summary(data: PropertyData) -> str:
    free_public_source = data.state == "MN" and "public" in data.source.lower()
    unavailable = (
        "Not available from free public source" if free_public_source else "Not available"
    )

    last_sold = unavailable
    if data.last_sold_price is not None and data.last_sold_date:
        last_sold = f"{_money(data.last_sold_price)} on {data.last_sold_date}"
    elif data.last_sold_price is not None:
        last_sold = _money(data.last_sold_price)
    elif data.last_sold_date:
        last_sold = data.last_sold_date

    lines = [
        "Property Lookup Result",
        "----------------------",
        f"Input Address: {data.input_address}",
        f"Normalized Address: {data.normalized_address}",
        f"State: {_text(data.state, unavailable)}",
        f"County: {_text(data.county, unavailable)}",
        f"Parcel ID: {_text(data.parcel_id, unavailable)}",
        f"Property Type: {_text(data.property_type, unavailable)}",
        f"Year Built: {_year(data.year_built, unavailable)}",
        f"Beds: {_number(data.beds, unavailable)}",
        f"Baths: {_number(data.baths, unavailable)}",
        f"Square Feet: {_number(data.square_feet, unavailable)}",
        f"Lot Size: {_area(data.lot_size, unavailable)}",
        f"Assessed Land Value: {_money(data.assessed_land_value, unavailable)}",
        f"Assessed Building Value: {_money(data.assessed_building_value, unavailable)}",
        f"Tax Assessed Value: {_money(data.tax_assessed_value, unavailable)}",
        f"Annual Property Tax: {_money(data.annual_property_tax, unavailable)}",
        f"Estimated Market Value: {_money(data.estimated_market_value, unavailable)}",
        f"List Price: {_money(data.list_price, unavailable)}",
        f"Last Sold: {last_sold}",
        f"Source: {data.source}",
        f"Source URL: {_text(data.source_url, unavailable)}",
        f"Lookup Time: {_timestamp(data.lookup_timestamp)}",
    ]
    coverage_message = data.raw_data.get("coverage_message")
    if coverage_message:
        lines.append(f"Coverage Note: {coverage_message}")
    if data.unavailable_fields:
        lines.append(f"Unavailable Fields: {', '.join(data.unavailable_fields)}")
    return "\n".join(lines)


def _text(value: object | None, unavailable: str = "Not available") -> str:
    return str(value) if value not in (None, "") else unavailable


def _number(
    value: float | int | None, unavailable: str = "Not available"
) -> str:
    if value is None:
        return unavailable
    number = float(value)
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.1f}"


def _year(value: int | None, unavailable: str = "Not available") -> str:
    return str(value) if value is not None else unavailable


def _money(value: float | int | None, unavailable: str = "Not available") -> str:
    return f"${float(value):,.0f}" if value is not None else unavailable


def _area(value: float | int | None, unavailable: str = "Not available") -> str:
    return f"{_number(value)} sqft" if value is not None else unavailable


def _timestamp(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
