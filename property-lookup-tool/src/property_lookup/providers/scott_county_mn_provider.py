"""Backward-compatible import for the relocated Scott County provider."""

from property_lookup.providers.mn.county_providers.scott_county_provider import (
    ScottCountyProvider,
)

ScottCountyMNProvider = ScottCountyProvider

__all__ = ["ScottCountyMNProvider"]
