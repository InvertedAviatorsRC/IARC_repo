import pytest

from property_lookup.config import ConfigurationError, Settings
from property_lookup.models import PropertyData
from property_lookup.providers.base import PropertyProvider
from property_lookup.services.property_service import PropertyService, build_property_service


class RecordingProvider(PropertyProvider):
    def __init__(self):
        self.address = None

    def lookup_property(self, address: str) -> PropertyData:
        self.address = address
        return PropertyData(address, address, source="Test")


def test_property_service_calls_selected_provider():
    provider = RecordingProvider()
    result = PropertyService(provider).lookup("10 Test Ave, Austin, TX")

    assert provider.address == "10 Test Ave, Austin, TX"
    assert result.source == "Test"


def test_missing_rentcast_api_key_has_clear_error():
    with pytest.raises(ConfigurationError, match="RENTCAST_API_KEY"):
        build_property_service(Settings(property_provider="rentcast"))
