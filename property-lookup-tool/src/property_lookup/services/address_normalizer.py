"""Small, provider-neutral address cleanup helpers."""

import re


def normalize_address(address: str) -> str:
    """Clean whitespace without guessing or changing address components."""
    cleaned = re.sub(r"\s+", " ", address).strip(" ,")
    if not cleaned:
        raise ValueError("Address cannot be empty.")
    return re.sub(r"\s*,\s*", ", ", cleaned)
