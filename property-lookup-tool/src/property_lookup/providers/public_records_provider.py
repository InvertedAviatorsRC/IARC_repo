"""Placeholder for a future public-records integration."""

from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider


class PublicRecordsProvider(PropertyProvider):
    def lookup_property(self, address: str) -> PropertyData:
        raise NotImplementedError(
            "PublicRecordsProvider is planned for a future version and is not yet configured."
        )
