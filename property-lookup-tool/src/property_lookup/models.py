"""Application data models."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class PropertyData:
    """A provider-neutral summary of a residential property."""

    input_address: str
    normalized_address: str
    state: str | None = None
    county: str | None = None
    parcel_id: str | None = None
    property_type: str | None = None
    year_built: int | None = None
    beds: float | None = None
    baths: float | None = None
    square_feet: float | None = None
    lot_size: float | None = None
    assessed_land_value: float | None = None
    assessed_building_value: float | None = None
    tax_assessed_value: float | None = None
    annual_property_tax: float | None = None
    last_sold_date: str | None = None
    last_sold_price: float | None = None
    estimated_market_value: float | None = None
    list_price: float | None = None
    source: str = "Unknown"
    source_url: str | None = None
    lookup_timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    unavailable_fields: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)

    # Optional paid providers may supply rent even though public records usually do not.
    rent_estimate: float | None = None

    def refresh_unavailable_fields(self) -> "PropertyData":
        """Record display fields for which no source supplied a value."""
        display_fields = (
            "parcel_id",
            "property_type",
            "year_built",
            "beds",
            "baths",
            "square_feet",
            "lot_size",
            "assessed_land_value",
            "assessed_building_value",
            "tax_assessed_value",
            "annual_property_tax",
            "last_sold_date",
            "last_sold_price",
            "estimated_market_value",
            "list_price",
        )
        self.unavailable_fields = [
            name for name in display_fields if getattr(self, name) is None
        ]
        return self
