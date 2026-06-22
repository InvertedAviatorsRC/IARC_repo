"""Human-readable terminal output."""

from datetime import datetime

from property_lookup.models import PropertyData


def format_property_summary(data: PropertyData) -> str:
    last_sold = "Not available"
    if data.last_sold_price is not None and data.last_sold_date:
        last_sold = f"{_money(data.last_sold_price)} on {data.last_sold_date}"
    elif data.last_sold_price is not None:
        last_sold = _money(data.last_sold_price)
    elif data.last_sold_date:
        last_sold = data.last_sold_date

    free_public_source = data.source == "Scott County MN public parcel data"
    market_unavailable = (
        "Not available from free public source"
        if free_public_source
        else "Not available"
    )

    lines = [
        "Property Lookup Result",
        "----------------------",
        f"Input Address: {data.input_address}",
        f"Normalized Address: {data.normalized_address}",
        f"Parcel ID: {_text(data.parcel_id)}",
        f"Property Type: {_text(data.property_type)}",
        f"Year Built: {_year(data.year_built)}",
        f"Beds: {_number(data.beds)}",
        f"Baths: {_number(data.baths)}",
        f"Square Feet: {_number(data.square_feet)}",
        f"Lot Size: {_area(data.lot_size)}",
        f"Estimated Value: {_money(data.estimated_value, market_unavailable)}",
        f"Rent Estimate: {_rent(data.rent_estimate)}",
        f"List Price: {_money(data.list_price, market_unavailable)}",
        f"Last Sold: {last_sold}",
        f"Tax Assessed Value: {_money(data.tax_assessed_value)}",
        f"Annual Property Tax: {_money(data.annual_property_tax)}",
        f"Source: {data.source}",
        f"Lookup Time: {_timestamp(data.lookup_timestamp)}",
    ]
    for index, url in enumerate(data.source_urls, start=1):
        label = "Source URL" if index == 1 else f"Source URL {index}"
        lines.append(f"{label}: {url}")
    return "\n".join(lines)


def _text(value: object | None) -> str:
    return str(value) if value not in (None, "") else "Not available"


def _number(value: float | int | None) -> str:
    if value is None:
        return "Not available"
    number = float(value)
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.1f}"


def _year(value: int | None) -> str:
    return str(value) if value is not None else "Not available"


def _money(value: float | int | None, unavailable: str = "Not available") -> str:
    return f"${float(value):,.0f}" if value is not None else unavailable


def _rent(value: float | int | None) -> str:
    return f"{_money(value)}/month" if value is not None else "Not available"


def _area(value: float | int | None) -> str:
    return f"{_number(value)} sqft" if value is not None else "Not available"


def _timestamp(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
