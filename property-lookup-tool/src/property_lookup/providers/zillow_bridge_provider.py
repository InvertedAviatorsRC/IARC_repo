"""Placeholder for a future licensed Zillow bridge integration."""

from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider


class ZillowBridgeProvider(PropertyProvider):
    def lookup_property(self, address: str) -> PropertyData:
        raise NotImplementedError(
            "ZillowBridgeProvider is planned for a future version and must use an "
            "authorized API integration; direct Zillow page scraping is not supported."
        )
