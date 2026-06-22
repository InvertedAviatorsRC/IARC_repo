# Property Lookup Tool

A local-first Python command-line program for looking up Minnesota residential
property records by address. The default path is **free and requires no API key or
paid subscription**.

Version 1 uses an official public-data pipeline:

1. Normalize the address.
2. Match it with the free U.S. Census geocoder and identify its Minnesota county.
3. Query Minnesota Geospatial Commons' statewide opt-in parcel FeatureServer.
4. Try MetroGIS regional parcels when applicable and needed.
5. Enrich the result with a county-specific provider when one is implemented.
6. Return every real field found and mark the rest unavailable.

The project does **not** scrape Zillow, automate browsers, bypass anti-bot systems,
or use hidden/restricted endpoints. Providers use official public machine-readable
services or authorized APIs.

## Install

Python 3.10 or newer is required. From `property-lookup-tool/`:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Free Minnesota lookup

Copy the environment template:

```bash
cp .env.example .env
```

The default configuration needs no credential:

```dotenv
PROPERTY_PROVIDER=minnesota_public
RENTCAST_API_KEY=
```

Run a lookup:

```bash
python -m property_lookup.cli "12649 Monterey Ave S, Savage, MN 55378"
```

The default provider uses these public sources:

- [U.S. Census Geocoder](https://geocoding.geo.census.gov/geocoder/) for address,
  coordinates, state, and county identification.
- [Minnesota Geospatial Commons statewide opt-in parcels](https://gis.data.mn.gov/maps/69148d3959194a05a23964cc60f6517b/about)
  for standardized parcel and tax fields where a county participates.
- [MetroGIS regional parcels](https://arcgis.metc.state.mn.us/data1/rest/services/parcels/Parcels/FeatureServer)
  as a seven-county Twin Cities fallback.
- Official county ArcGIS/open-data services for local enrichment. Scott County is
  the first implemented county adapter.

Public coverage varies by county and by field. A county may omit building details,
tax totals, or sale history, and not every Minnesota county currently participates
in the statewide compilation. When a parcel or county adapter is unavailable, the
program returns the verified address/county and any broad-source fields it found,
plus a coverage note. It does not crash simply because local data is limited.

Free public records usually do not include a Zestimate-style automated valuation,
current listing price, or rent estimate. Those fields display as
`Not available from free public source`; the program never invents them.

## Provider architecture

The Minnesota router lives under `src/property_lookup/providers/mn/`:

```text
mn/
  minnesota_public_provider.py      # geocoder and routing pipeline
  mn_geospatial_commons_provider.py # statewide opt-in parcels
  metrogis_provider.py              # seven-county regional fallback
  county_provider_registry.py       # implemented county adapters
  county_providers/
    scott_county_provider.py        # working county enrichment
    hennepin_county_provider.py     # explicit future placeholders
    ramsey_county_provider.py
    dakota_county_provider.py
    washington_county_provider.py
    anoka_county_provider.py
    carver_county_provider.py
```

Each new county provider can be implemented independently and then registered in
`county_provider_registry.py`. Placeholder classes raise `NotImplementedError`;
they do not pretend to return real data.

## Optional paid nationwide provider

RentCast remains available for broader national coverage, but it is **not the
default** and requires an active paid API subscription/key:

```dotenv
PROPERTY_PROVIDER=rentcast
RENTCAST_API_KEY=your_active_key_here
```

`.env` is ignored by Git. Never commit a real key. If the key is missing or
rejected, the CLI reports the problem honestly.

## Explicit mock mode

Use stable sample data without making any network request:

```bash
python -m property_lookup.cli "123 Main St, Philadelphia, PA" --mock
```

`--mock` always overrides `PROPERTY_PROVIDER`.

## Tests

```bash
pytest
```

Tests cover Minnesota county routing, statewide parcel mapping, Scott County
enrichment, unsupported-county partial results, unavailable-field output, mock
mode, the CLI, and optional RentCast behavior. Automated tests stub HTTP responses
and do not depend on live public services.

## Future directions

Natural next steps are implementing the placeholder metro county adapters, adding
adapters for non-metro counties, supporting a locally downloaded MnGeo GeoPackage
for offline/batch use, CSV export, caching, reports, a desktop/web UI, and packaged
executables.
