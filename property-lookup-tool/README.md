# Property Lookup Tool

A local-first Python command-line program for looking up real property records by
address. Version 1 is designed to work **free, without an API key or paid
subscription**, by querying official county/open-data services where available.

The first working provider uses Scott County, Minnesota's public ArcGIS parcel
layer. It returns real county fields such as parcel ID, property classification,
year built, bedrooms, bathrooms, living area, lot area, county estimated market
value, and last sale data when those fields exist.

Public records are not the same as commercial market data. Free county data may
not include a Zestimate-style valuation, current listing price, rent estimate, or
annual tax bill. The CLI says `Not available` instead of inventing a value or
failing the entire lookup. Data fields and update schedules vary by county.

This project does **not** scrape Zillow pages. It does not use browser automation,
private endpoints, proxies, CAPTCHA bypasses, or restricted county pages. Providers
use official public machine-readable sources or authorized APIs.

## Branch and project location

The project lives in the IARC repository under `property-lookup-tool/` on:

```text
feature/property-lookup-tool
```

Do not make these changes directly on `main`.

## Install

Python 3.10 or newer is required. From this directory:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Free Scott County lookup

Copy the default configuration:

```bash
cp .env.example .env
```

The default `.env` setting needs no credential:

```dotenv
PROPERTY_PROVIDER=scott_county_mn
RENTCAST_API_KEY=
```

Run the test-address lookup:

```bash
python -m property_lookup.cli "12649 Monterey Ave S, Savage, MN 55378"
```

`ScottCountyMNProvider` queries the official
[Scott County parcel ArcGIS layer](https://gis.co.scott.mn.us/arcgis/rest/services/AGOL/SC_PARCELS_AGOL_WM/MapServer/0).
It first requests records with the same numeric house number, then performs an
exact normalized street and ZIP match locally. Only needed property fields are
requested; taxpayer names and mailing addresses are not requested. The source name
and public URLs are preserved in both the result and CLI output.

This provider supports Scott County, Minnesota only. A lookup elsewhere will give
a clear county/provider message. Future county providers can follow the same
interface, but their fields will differ because local open-data programs vary.

## Optional RentCast provider

RentCast remains available for broader US coverage, but it is **not the default**
and requires an active RentCast API subscription/key. To opt in, add a valid key:

```dotenv
PROPERTY_PROVIDER=rentcast
RENTCAST_API_KEY=your_active_key_here
```

Then run:

```bash
python -m property_lookup.cli "5500 Grand Lake Dr, San Antonio, TX 78244"
```

If the key is missing or rejected, the CLI reports the problem honestly. `.env` is
ignored by Git; never commit a real key.

## Explicit mock mode

Use stable sample data to test the application flow without a network request:

```bash
python -m property_lookup.cli "123 Main St, Philadelphia, PA" --mock
```

`--mock` always overrides `PROPERTY_PROVIDER`. Mock data is otherwise used only
when `PROPERTY_PROVIDER=mock` is explicitly configured.

## Provider selection and design

The current selector supports:

- `PROPERTY_PROVIDER=scott_county_mn` — free Scott County public parcel data
- `PROPERTY_PROVIDER=rentcast` — optional paid API integration
- `PROPERTY_PROVIDER=mock` — explicit sample data
- `PROPERTY_PROVIDER=zillow_bridge` — honest, unimplemented authorized-API placeholder
- `PROPERTY_PROVIDER=public_records` — honest, unimplemented generic placeholder

Every provider implements `PropertyProvider.lookup_property(address)` and returns a
provider-neutral `PropertyData` object. Selection happens in
`services/property_service.py`.

To add another county or provider:

1. Add a provider under `src/property_lookup/providers/`.
2. Use an official open-data download, ArcGIS REST, CSV, GeoJSON, or an authorized
   API, and review its terms.
3. Add its configuration and selector entry.
4. Map only real available fields into `PropertyData`, retain source metadata in
   `raw_data`, and add tests with stubbed HTTP responses.

## Tests

```bash
pytest
```

Tests cover the Scott County record mapping and safe address matching, default
provider selection, mock mode, service delegation, RentCast missing-key handling,
CLI output, formatting, and RentCast response merging. Automated tests do not make
live network requests.

## Future directions

Natural next steps include additional free county providers, a downloadable
Minnesota Geospatial Commons fallback, CSV and batch lookup, opt-in caching, pretty
reports, a desktop/web UI, and PyInstaller packaging. Paid providers such as
RentCast can remain optional for broader national coverage when a subscription is
useful.
