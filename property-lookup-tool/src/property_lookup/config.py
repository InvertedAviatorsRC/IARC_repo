"""Environment-based application configuration."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigurationError(ValueError):
    """Raised when required local configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    property_provider: str = "scott_county_mn"
    rentcast_api_key: str | None = None

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        return cls(
            property_provider=os.getenv("PROPERTY_PROVIDER", "scott_county_mn")
            .strip()
            .lower(),
            rentcast_api_key=os.getenv("RENTCAST_API_KEY") or None,
        )
