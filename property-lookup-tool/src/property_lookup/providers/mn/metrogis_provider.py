"""MetroGIS regional parcel fallback for the seven-county Twin Cities metro."""

import requests

from property_lookup.models import PropertyData
from property_lookup.providers.mn.mn_geospatial_commons_provider import (
    MNGeospatialCommonsProvider,
)


class MetroGISProvider(MNGeospatialCommonsProvider):
    """Query a county layer in MetroGIS's public regional parcel service."""

    BASE_URL = (
        "https://arcgis.metc.state.mn.us/data1/rest/services/"
        "parcels/Parcels/FeatureServer"
    )
    LAYER_IDS = {
        "anoka": 0,
        "carver": 1,
        "dakota": 2,
        "hennepin": 3,
        "ramsey": 4,
        "scott": 5,
        "washington": 6,
    }
    SOURCE_NAME = "MetroGIS regional public parcel data"

    def __init__(
        self,
        session: requests.Session | None = None,
        timeout: float = 25.0,
    ) -> None:
        super().__init__(session=session, timeout=timeout)

    def lookup_property(
        self,
        address: str,
        latitude: float,
        longitude: float,
        county: str,
    ) -> PropertyData | None:
        county_key = county.lower().replace(" county", "").strip()
        layer_id = self.LAYER_IDS.get(county_key)
        if layer_id is None:
            return None
        self.LAYER_URL = f"{self.BASE_URL}/{layer_id}"
        return super().lookup_property(address, latitude, longitude, county)
