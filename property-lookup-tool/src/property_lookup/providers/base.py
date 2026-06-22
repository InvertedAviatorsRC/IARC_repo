"""Interfaces and shared errors for property providers."""

from abc import ABC, abstractmethod

from property_lookup.models import PropertyData


class ProviderError(RuntimeError):
    """Raised when a provider cannot complete a lookup."""


class PropertyProvider(ABC):
    """Contract implemented by every property-data provider."""

    @abstractmethod
    def lookup_property(self, address: str) -> PropertyData:
        """Look up one address and return provider-neutral property data."""
