"""Provider selection and lookup orchestration."""

from property_lookup.config import ConfigurationError, Settings
from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider
from property_lookup.providers.mock_provider import MockProvider
from property_lookup.providers.public_records_provider import PublicRecordsProvider
from property_lookup.providers.rentcast_provider import RentCastProvider
from property_lookup.providers.mn import MinnesotaPublicProvider
from property_lookup.providers.zillow_bridge_provider import ZillowBridgeProvider


class PropertyService:
    def __init__(self, provider: PropertyProvider) -> None:
        self.provider = provider

    def lookup(self, address: str) -> PropertyData:
        return self.provider.lookup_property(address)


def build_property_service(settings: Settings, force_mock: bool = False) -> PropertyService:
    provider_name = "mock" if force_mock else settings.property_provider

    if provider_name == "mock":
        provider: PropertyProvider = MockProvider()
    elif provider_name == "minnesota_public":
        provider = MinnesotaPublicProvider()
    elif provider_name == "rentcast":
        if not settings.rentcast_api_key:
            raise ConfigurationError(
                "A RentCast API key is required. Copy .env.example to .env, set "
                "RENTCAST_API_KEY, and try again. Use --mock to test without an API key."
            )
        provider = RentCastProvider(settings.rentcast_api_key)
    elif provider_name == "zillow_bridge":
        provider = ZillowBridgeProvider()
    elif provider_name == "public_records":
        provider = PublicRecordsProvider()
    else:
        raise ConfigurationError(
            f"Unknown PROPERTY_PROVIDER '{provider_name}'. Supported values: "
            "minnesota_public, rentcast, mock, zillow_bridge, public_records."
        )

    return PropertyService(provider)
