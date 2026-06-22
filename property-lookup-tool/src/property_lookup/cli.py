"""Command-line entry point for property lookup."""

import argparse
import sys
from collections.abc import Sequence

from property_lookup.config import ConfigurationError, Settings
from property_lookup.output.formatters import format_property_summary
from property_lookup.providers.base import ProviderError
from property_lookup.services.property_service import build_property_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="property-lookup",
        description="Look up real-estate property records and valuation data by address.",
    )
    parser.add_argument("address", help="Full US property address")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use explicit sample data instead of making a provider API request",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_environment()
        service = build_property_service(settings, force_mock=args.mock)
        result = service.lookup(args.address)
    except (ConfigurationError, ProviderError, NotImplementedError, ValueError) as exc:
        print(f"Property lookup failed: {exc}", file=sys.stderr)
        return 2

    print(format_property_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
