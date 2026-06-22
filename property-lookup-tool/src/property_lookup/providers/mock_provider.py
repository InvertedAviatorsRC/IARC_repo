"""Explicit test/demo provider that makes no network requests."""

from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider
from property_lookup.services.address_normalizer import normalize_address


class MockProvider(PropertyProvider):
    """Return stable sample data only when mock mode is explicitly selected."""

    def lookup_property(self, address: str) -> PropertyData:
        normalized = normalize_address(address)
        return PropertyData(
            input_address=address,
            normalized_address=normalized,
            year_built=1952,
            estimated_value=325_000,
            rent_estimate=2_150,
            beds=3,
            baths=2,
            square_feet=1_450,
            lot_size=3_200,
            property_type="Single Family",
            last_sold_date="2021-06-15",
            last_sold_price=265_000,
            tax_assessed_value=240_000,
            annual_property_tax=4_200,
            source="Mock (sample data)",
            raw_data={"mock": True},
        )
