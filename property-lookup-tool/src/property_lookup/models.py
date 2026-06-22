"""Application data models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class PropertyData:
    """A provider-neutral summary of a residential property."""

    input_address: str
    normalized_address: str
    year_built: int | None = None
    list_price: float | None = None
    estimated_value: float | None = None
    rent_estimate: float | None = None
    beds: float | None = None
    baths: float | None = None
    square_feet: float | None = None
    lot_size: float | None = None
    property_type: str | None = None
    last_sold_date: str | None = None
    last_sold_price: float | None = None
    tax_assessed_value: float | None = None
    annual_property_tax: float | None = None
    source: str = "Unknown"
    lookup_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    raw_data: dict[str, Any] = field(default_factory=dict)
