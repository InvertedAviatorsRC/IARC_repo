"""Registry for Minnesota county-specific public data adapters."""

import requests

from property_lookup.providers.base import PropertyProvider
from property_lookup.providers.mn.county_providers.scott_county_provider import (
    ScottCountyProvider,
)


class CountyProviderRegistry:
    """Return implemented county adapters without pretending placeholders work."""

    PROVIDERS: dict[str, type[PropertyProvider]] = {
        "scott": ScottCountyProvider,
    }

    def get_provider(
        self, county: str, session: requests.Session | None = None
    ) -> PropertyProvider | None:
        key = county.lower().replace(" county", "").strip()
        provider_class = self.PROVIDERS.get(key)
        return provider_class(session=session) if provider_class else None

    def is_implemented(self, county: str) -> bool:
        key = county.lower().replace(" county", "").strip()
        return key in self.PROVIDERS
