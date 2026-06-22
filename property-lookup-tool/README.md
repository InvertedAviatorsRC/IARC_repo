# Property Lookup Tool

A local-first Python command-line program that looks up US real-estate property
records and value estimates by address. Version 1 uses the legitimate RentCast API
and keeps provider-specific code behind a small interface so a desktop app, web UI,
batch workflow, or another licensed/public-records provider can be added later.

This project does **not** scrape Zillow pages. It does not use browser automation,
private endpoints, proxies, or CAPTCHA bypasses. The `ZillowBridgeProvider` file is
only a placeholder for a future authorized API integration.

## Branch and project location

The project lives in the IARC repository under `property-lookup-tool/` and is
developed on:

```text
feature/property-lookup-tool
```

To create the branch manually from a current checkout:

```bash
git fetch origin main
git switch -c feature/property-lookup-tool origin/main
cd property-lookup-tool
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

The editable install makes the `src/` package available while you develop it.

## Configure a real lookup

1. Create a RentCast account and API key from the
   [RentCast API dashboard](https://app.rentcast.io/app/api).
2. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and add the key:

   ```dotenv
   PROPERTY_PROVIDER=rentcast
   RENTCAST_API_KEY=your_key_here
   ```

`.env` is ignored by Git. Never commit a real key.

Run a real lookup:

```bash
python -m property_lookup.cli "5500 Grand Lake Dr, San Antonio, TX 78244"
```

RentCast is called once for the property record and once for the value estimate.
The responses are merged into one `PropertyData` result. Missing fields display as
`Not available`; they are never replaced with invented values. Provider responses
are retained in `raw_data` for future export/report features, but raw data is not
printed by the CLI.

If the key is absent or rejected, the command exits with a clear error instead of
pretending the lookup succeeded.

## Explicit mock mode

Use stable sample data to test the local flow without spending an API request:

```bash
python -m property_lookup.cli "123 Main St, Philadelphia, PA" --mock
```

Mock data is used only with `--mock` or `PROPERTY_PROVIDER=mock`.

## Provider design

Every provider implements `PropertyProvider.lookup_property(address)` and returns a
provider-neutral `PropertyData` object. Selection happens in
`services/property_service.py`.

To add a provider:

1. Add a class under `src/property_lookup/providers/` that implements
   `PropertyProvider`.
2. Read its credentials in `config.py` and add only blank variables to
   `.env.example`.
3. Add it to `build_property_service()`.
4. Map the provider response into `PropertyData`, keep the original response in
   `raw_data`, and add tests with stubbed HTTP responses.

`ZillowBridgeProvider` and `PublicRecordsProvider` intentionally raise
`NotImplementedError`. They are honest extension points, not fake providers.

## Tests

```bash
pytest
```

Tests cover mock mode, service delegation, missing-key errors, CLI output, readable
formatting, and RentCast response merging without making live network requests.

## Future directions

The service/model/provider split is ready to sit behind a simple desktop GUI or web
UI. Natural next steps include CSV export, batch lookups, opt-in caching, formatted
reports, and packaging with PyInstaller. Provider terms and data-retention rules
should be reviewed before adding caching, exports, or redistribution.
