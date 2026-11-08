# Data generation and package maintenance

[Back to the project README](../README.md)

## Daily snapshots

This repository generates matching cumulative CSV and Excel files every day:

```text
output/eurofxref_and_crypto_rates.YYYY.MM.DD.csv
output/eurofxref_and_crypto_rates.YYYY.MM.DD.xlsx
```

Each snapshot contains **all dates from the ECB historical start (1999-01-04)
through the day before the snapshot's run date**, newest first. The filename's
date is the **run date**, using Europe/Amsterdam local time, not the last data date.

### Completed days only

Both CSV and Excel end yesterday. Crypto uses completed daily closing prices,
not live intraday prices, so the unfinished current day is excluded for all
currencies. At the daily 16:30 Europe/Amsterdam update on October 24, 2026, the
files are named `eurofxref_and_crypto_rates.2026.10.24.csv` and `.xlsx`, and their
newest data row is **2026-10-23**.

Today's ECB fiat rates are also withheld until tomorrow's snapshot, even if
already published. Weekend and holiday rows remain in the calendar: fiat stays
blank when the ECB publishes no rate, while crypto is included when available.
For example, Sunday's snapshot includes Saturday's crypto closing prices and
blank Saturday fiat cells. Missing source observations can still leave gaps and
are retried on later runs.

`--run-date YYYY-MM-DD` overrides the run date and applies the same rule: data
ends the preceding calendar day. Existing cached rows from the run date or later
are excluded. The script logs the last data date when it creates the files.

Both formats contain the same dates and currency columns, with no empty separator
column. Excel uses a `Rates` sheet with numeric rates, real date cells displayed as
`YYYY-MM-DD`, and two header rows: symbols followed by full currency names.
Names link to currency-specific ECB rate pages or the exact CoinMarketCap page.
Both header rows and the date column are frozen; filters use the name row.
Data starts on row 3. Missing
values stay blank and download failures remain the text `ERROR`. CSV files remain
the cache used by subsequent daily runs. The daily action commits both formats.
Both CSV and Excel display rates as plain decimals, never scientific notation,
including small values such as BTC (`0.0000138166606522`, not `1.38166606522e-05`).
CSV conversion expands exponent notation without rounding existing decimal digits;
Excel cells retain their underlying numeric values.

## Output semantics

The file preserves the ECB convention consistently across fiat and crypto:

> **each rate is the number of units of that currency/asset equal to 1 EUR**

So:

- `USD = 1.1205` means `1 EUR = 1.1205 USD`
- `BTC = 0.0000143` means `1 EUR = 0.0000143 BTC`

This consistency makes downstream conversion simple:

```python
amount_eur = amount_in_original_currency / rate
```

### Missing values

- **Fiat blank**: ECB did not publish a reference rate for that calendar date
  (typically weekends, TARGET/bank holidays, or a currency not yet/any longer
  covered). Fiat values are **not carried forward**.
- **Crypto blank**: the date is before CoinMarketCap's `first_historical_data`
  for that coin, or CoinMarketCap genuinely returned no observation.
- **Crypto `ERROR`**: the script attempted to obtain that crypto period but the
  request failed or appeared to be blocked/rate-limited after three attempts.

A later successful run retries both missing and `ERROR` crypto cells.
Once a coin's historical start is known, cached cells before that date are
cleared, including errors left by an earlier failed asset lookup.

### USD retry when EUR history is missing

EUR quotes are preferred. After the EUR download attempts, the script retries
unresolved dates in USD when a valid **same-day ECB USD reference rate** exists.
This applies to both the official API and the public website endpoint, including
partial EUR responses and failed EUR requests. Existing cached rates and valid
EUR observations are preserved.

The output convention stays **coins per EUR**:

```text
coins per EUR = ECB USD per EUR / CoinMarketCap USD per coin
```

For example, an ECB rate of 1.0561 USD per EUR and a coin price of 20,000 USD
produce 0.000052805 coins per EUR. This uses two reference sources, so the result
may differ slightly from a direct CoinMarketCap EUR quote.

ECB rates are never carried forward for this conversion. If the same-day USD
reference rate is missing (such as weekends or holidays), no USD retry is made.
If neither source returns an observation, the cell stays blank; a failed request
leaves `ERROR`. Both are retried on later runs. The unfinished current day is
excluded from the snapshot entirely.

The USD retry repairs source gaps such as June 28–29, 2022, where CoinMarketCap's
EUR history is missing observations present in its USD history. It runs during
the normal daily update; older snapshot files are not rewritten automatically.

## Why missed GitHub Actions runs are repaired automatically

The script does **not** assume yesterday's Action succeeded.

Every run:

1. checks cached ECB historical and daily data against the publication schedule,
   downloading missing, invalid, or stale files;
2. combines the full historical data with the latest daily row;
3. creates a complete daily calendar through yesterday;
4. uses the latest existing output snapshot as a crypto cache;
5. detects every missing/`ERROR` crypto date;
6. downloads those missing crypto windows;
7. writes a new cumulative snapshot.

Therefore, if GitHub Actions fails for 10 days, the next successful run fills the
10-day window rather than only downloading one day.

## Asset configuration

### Fiat metadata in `assets.json`

The first group, `fiat`, describes the 41 currency columns in the ECB historical
and daily exports, including discontinued currencies. Each entry contains its
`symbol`, the full name from the ECB's official `CL_CURRENCY` code list,
`ecb_url` (the shared daily ZIP download), and `ecb_rates_url` (its currency-specific
ECB rate page, used by the Excel name hyperlink).

This group is informational only. It does not trigger per-currency downloads,
add rows or rate columns, or feed fiat entries into the CMC resolver. Fiat rates
continue to come from the combined ECB exports and their existing cache.
Additional sources may be integrated separately in future; adding metadata alone
does not enable a new rate source. `add_asset.py` preserves this group and avoids
using its symbols for new crypto column names.

### Crypto assets

The initial configured set is 20 major cryptocurrencies plus 5 major stablecoins
in `assets.json`. Additional coins can be added by their unique CMC URL.

### Add an asset by URL

```bash
python add_asset.py 'https://coinmarketcap.com/currencies/tontoken/'
```

The tool reads that specific CMC page to obtain its unique ID, canonical URL,
current name/ticker, and first historical date. It never searches by name or
ticker. It adds the coin to `major_cryptocurrencies` by default; use
`--group stablecoins` for a stablecoin or `--config /path/to/assets.json` for
another configuration. Existing records are preserved, and an already configured
CMC ID is reported without adding a duplicate, even if its name or URL changed.

`symbol` is the unique CSV/Excel column name. If a ticker is already in use, the
new column becomes `TICKER_CMCID`. For example, adding TON Token (CMC 6890) creates
`TON_6890` and leaves the existing `TON` column (Gram/former Toncoin, CMC 11419)
unchanged. The original ticker is stored as `cmc_symbol`. Repeated names are
allowed; output column names must be unique. Known fiat columns in the latest
snapshot are also checked for collisions.

Preview without editing the configuration, or choose a different column name:

```bash
python add_asset.py 'https://coinmarketcap.com/currencies/tontoken/' --dry-run
python add_asset.py 'https://coinmarketcap.com/currencies/tontoken/' --symbol TON_TOKEN
```

Failed page downloads, invalid URLs, and missing historical metadata leave the
configuration untouched. Config updates are written atomically. The next normal
`rates.py` run fetches the new coin's history; existing snapshots are not rewritten
by `add_asset.py`. Commit the changed `assets.json` to make the asset available to
the scheduled GitHub action.

Crypto assets specify `cmc_id` and `first_historical_date` in
`assets.json`, verified against CoinMarketCap's asset metadata
(`actualTimeStart`). Daily runs use these fixed IDs directly and make no asset
map requests. Historical price downloads can still fail or be rate-limited;
missing and `ERROR` cells are retried on later runs.

IDs and start dates were verified on 2026-10-24 using CoinMarketCap's
`/data-api/v3/cryptocurrency/detail?id=<cmc_id>` metadata endpoint. The `TON`
output column retains its existing name and uses ID 11419, currently listed
by CoinMarketCap as "Gram (prev. Toncoin)" (`GRAM`).

On 2026-10-29, the TON column in the published CSV and Excel snapshots was
rechecked and corrected against CMC ID 11419. Earlier cached values had come
from the unrelated TON Token (ID 6890); changing the configured ID had not
replaced those cached numbers. The repaired series uses the inverse of ID
11419's daily EUR closing price, with USD/ECB conversion for June 28–29, 2022.
Dates before its first historical observation (2021-08-26) are blank. The column
name remains `TON`; values are coins per EUR. Other currency columns are unchanged.

For newly added assets without both fields, the script falls back to the asset
map, paginating to include newer assets and using the authenticated API when
`CMC_API_KEY` is set. Add a verified ID and historical start date to keep new
assets independent of that lookup too.

### Recommended: official CoinMarketCap API

Create a GitHub repository secret named:

```text
CMC_API_KEY
```

When present, the script uses CoinMarketCap's official historical quotes API and
requests EUR conversion directly.

**Important:** how far back the API actually allows you to query depends on your
CoinMarketCap plan. The script asks for the full available range, but it cannot
override plan limits.

### Free fallback

If `CMC_API_KEY` is absent, the script uses CoinMarketCap's public website
historical-data endpoint. This endpoint is not the documented Pro API and may
change or apply anti-bot controls.

To reduce the chance of blocking, the script:

- sends a descriptive User-Agent;
- makes requests serially (no concurrency);
- pauses between requests;
- requests only missing periods;
- uses moderate 180-day chunks;
- retries at most three times with backoff;
- uses explicit connect/read timeouts.

If a crypto window is blocked or fails after the three attempts, the script does
not fabricate or carry forward a rate: it writes `ERROR` for the affected crypto
cells.

## ECB behavior

The ECB daily CSV can use a human-readable date such as:

```text
22 October 2026
```

while the historical CSV uses ISO dates:

```text
2026-10-22
```

`rates.py` normalizes both to `YYYY-MM-DD`.

The historical ECB file is the recovery source for missed runs. The daily file
is used as an additional freshness/overlay source.

### RUB after the ECB suspension: potential additional source

The ECB last published EUR/RUB on March 1, 2022; later RUB cells remain blank.
The Bank of Russia is a possible official source for filling that period in a
future integration. Its [XML interface](https://www.cbr.ru/development/sxml/)
provides historical EUR observations via `XML_dynamic.asp`, with currency ID
`R01239`, and the daily export via `XML_daily_eng.asp`. The historical endpoint
was checked against March 2022 and October 2026 observations on 2026-10-29.
Its `Value / Nominal` yields RUB per EUR, matching this project's rate convention.

This would be a source change: [ECB suspension](https://www.ecb.europa.eu/services/using-our-site/technical-updates/html/ecb.technical_update220302.en.html)
and [Bank of Russia methodology](https://www.cbr.ru/eng/press/pr/?file=638538938437943081ENG_PP.htm)
should be recorded alongside the series. CBR rates have their own effective dates
(normally the day after setting) and remain valid until superseded; these differ
from ECB observation dates and the current blank-on-nonpublication-days policy.
An integration must define that date mapping and source provenance explicitly.
This research does not enable CBR downloads or change any RUB values.

### ECB download cache and `--force`

Downloaded ZIPs are stored in `.cache/ecb/` (change this with `--ecb-cache-dir`).
Each file is checked independently against the latest expected release: around
16:00 Europe/Amsterdam on weekdays, excluding TARGET closing days (January 1,
Good Friday, Easter Monday, May 1, December 25 and 26). The calendar follows
daylight saving time. See the [ECB publication schedule](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)
and [TARGET closing days](https://www.ecb.europa.eu/ecb/contacts/working-hours/html/index.en.html).

If the latest date inside a cached file covers that release, it is reused without
a network request. Repeated runs, weekends, holidays, and runs before publication
therefore reuse current downloads. Existing `eurofxref-hist.zip`, `eurofxref.zip`,
or their unzipped `.csv` equivalents in the working directory are also recognized.
Missing, corrupt, or outdated files are downloaded and validated before replacing
their cache entries. If a source still returns old data after its expected release,
the next run retries it. Same-day corrections are picked up by the next scheduled
refresh or a forced download.

When nothing is downloaded, the script prints a reminder:

```text
No ECB downloads needed. Use --force to force an ECB download (explicit local CSV overrides stay local).
```

Run `python rates.py --force` to refresh both ZIPs regardless of freshness.
`--force` affects ECB downloads only; valid cached crypto rates remain preserved.
The explicit `--ecb-daily-file` and `--ecb-hist-file` options always use the supplied
local CSVs, including with `--force`. Freshness uses the actual clock; `--run-date`
only changes the snapshot's label and data cutoff.

GitHub Actions restores and saves `.cache/ecb` between runs, so fresh runners can
also skip unnecessary downloads. For manual runs, the Actions form includes a
**Force ECB ZIP downloads** option. If GitHub evicts the cache, the next run
downloads it again automatically. Cache files are not part of the exported data.

## GitHub Actions

The workflow runs daily at **16:30 Europe/Amsterdam** (CET in winter, CEST in
summer), half an hour after the ECB's usual 16:00 publication time. The rate-setting
procedure around 14:10 is earlier than publication; see the
[ECB reference-rate page](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html).
GitHub's schedule uses `cron: "30 16 * * *"` with `timezone: "Europe/Amsterdam"`
to follow daylight saving time automatically. GitHub may delay scheduled starts.
The workflow also runs on weekends for crypto data and can be started manually
from the Actions tab.

The workflow requires:

```yaml
permissions:
  contents: write
```

so that it can commit each generated snapshot back to `output/`.

If branch protection prevents direct pushes, change the workflow to open a pull
request instead.

## Local run

```bash
python -m pip install -r requirements.txt
python rates.py
```

For testing with local ECB files:

```bash
python rates.py \
  --run-date 2026-10-23 \
  --ecb-daily-file eurofxref.csv \
  --ecb-hist-file eurofxref-hist.csv
```

## Repository structure

```text
.
├── rates.py
├── assets.json
├── requirements.txt
├── README.md
├── .github/
│   └── workflows/
│       └── update-rates.yml
└── output/
    └── .gitkeep
```

## Operational note

For an air-gapped downstream environment, treat each dated CSV as an immutable
reference-data package. The filename itself identifies the snapshot date. Keep
the original transaction amount/currency and the rate/snapshot used for each
conversion so that later backfills are auditable.

## Build and publish a dated Python package

### Daily GitHub Actions wheel

The **Update ECB + crypto rates** workflow also tests the code, builds a wheel
with the generated CSV snapshot and Python conversion wrapper, and uploads it
as a workflow artifact named `offline-currency-coverter-wheel-RUN_ID-RUN_ATTEMPT`.
It also commits the wheel to `output/` alongside the CSV and Excel snapshot.
The wheel version follows the snapshot date (for example, a snapshot dated
`2026.11.09` produces `offlinecurrencycoverter-2026.11.9-py3-none-any.whl`;
Python packaging normalizes leading zeros in version numbers).
Download and unzip the artifact from the workflow run, then install the wheel:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install /path/to/offlinecurrencycoverter-YYYY.M.D-py3-none-any.whl

offline-currency-coverter currencies
offline-currency-coverter convert 100 USD EUR --date 2026-11-02 --date-window 0
# The same commands work through python -m offline_currency_coverter.
```

Conversion and currency listing use local or bundled data without network
requests. Both commands accept `--rates-path /path/to/snapshot.csv` or
`--output-dir /path/to/output`. Conversion prints an unrounded decimal amount;
see the rounding example above. With no date, the command uses the latest common observation. An explicit
`--date` requires an exact rate unless `--date-window` is supplied. The currency list includes EUR and every snapshot
symbol, including historical currencies; a listed currency may lack rates for
the requested date. Python callers can use:

```python
from offline_currency_coverter import convert, supported_currencies

print(supported_currencies())
print(convert("100", "USD", "EUR", "2026-11-02", 0))
```

To build the same wheel locally from an existing snapshot without fetching:

```sh
python -m pip install -r requirements-release.txt
python build_wheel.py
```

This build uses the newest CSV in `output/`, versions the package by that
snapshot's filename date, and writes to `dist/YYYY.MM.DD/`. Use `--output-dir`
or `--dist-dir` to choose other directories. Existing build directories are
rejected. The wheel preserves blanks and `ERROR` cells from the generated data;
conversion skips unusable rates. It bundles only the newest CSV, not Excel files.
The default version is date-only (`YYYY.M.D`). Rebuilding the same snapshot
in the daily workflow replaces its wheel in `output/`. To reinstall an updated
wheel with the same version, use `python -m pip install --force-reinstall
/path/to/the.whl`. An explicit `--revision N` is available when needed.
Dependencies must be installed from an accessible package index or wheelhouse.
Workflow artifacts are retained for 90 days; copy approved wheels to a private
GitHub Release or corporate package index for long-term installation.

### PyPI release

Install release tooling, then build and validate locally:

```sh
python -m pip install -r requirements-release.txt
python publish_package.py
```

The script first runs the fetcher for today (Europe/Amsterdam). A nonzero exit,
a missing current snapshot, or any `ERROR` download cells aborts the release
before building or uploading. Ordinary blank observations, such as weekend fiat
rates, remain allowed. Once fetching succeeds, it stages the package code, bundled asset configuration,
and **only the newest dated CSV** from `output/`. It builds a wheel and source
archive, then runs `twine check --strict`. Artifacts go into
`dist/YYYY.MM.DD/`. Source files are not modified. Excel files, caches, tests,
and credentials are excluded. The build date uses Europe/Amsterdam and can be
overridden with `--date 2026-11-03`. `--output-dir` selects the snapshot directory;
`--dist-dir` selects the artifact root. Existing release directories are rejected
so old artifacts cannot accidentally be uploaded.

To build, check, and upload to PyPI, configure a PyPI API token through Twine
(e.g. `TWINE_USERNAME=__token__` and `TWINE_PASSWORD` supplied securely through
your environment), then run:

```sh
python publish_package.py --publish --dist-dir publish-dist
# Or test the release against TestPyPI using a TestPyPI token:
python publish_package.py --publish --repository testpypi --dist-dir test-dist
```

The distribution name is `OfflineCurrencyCoverter`; your PyPI account must be allowed
to publish under that name. Authentication and upload errors fail the script.
Never commit API tokens. Without `--publish`, nothing is uploaded. PyPI versions
cannot be overwritten, so this scheme permits one release per calendar date.
The requested date version `2026.11.03` is normalized by Python packaging tools
to `2026.11.3`; these identify the same release.

After publication:

```sh
pip install OfflineCurrencyCoverter==2026.11.3
```

```python
from offline_currency_coverter import convert
amount = convert(100, "USD", "EUR", "2026-01-01", 10)
```

With no explicit data path, conversion selects the newest filename date across
local `output/` and the installed bundled data. An explicit `output_dir` or
`rates_path` uses only that location. Every release fetches fresh rates before building. `--date` changes the package
version only; the fetch still uses today. Check the snapshot filename printed
by the script. For environments with build tools already installed,
`--no-isolation` avoids downloading them into a separate build environment.

### Publish through GitHub Actions

`.github/workflows/publish-pypi.yml` provides a manual **Publish Python package to
PyPI** workflow. It tests the code, runs the mandatory fetch-and-build script,
and hands checked artifacts to a separate publishing job. Failed fetching,
`ERROR` cells, tests, or validation prevent publication. Only the default branch
can publish. The workflow has no push or pull-request trigger.

Use PyPI **Trusted Publishing** so GitHub needs no stored PyPI password or API
token. Configure these once:

1. Push this workflow and the packaging code to your GitHub repository.
2. In repository **Settings → Environments**, create an environment named `pypi`.
   Restrict deployments to the default branch.
3. In PyPI, open the project's **Publishing** settings and add a GitHub publisher.
   For a new project, use **Your account → Publishing → Add a new pending publisher**.
   Enter your actual GitHub owner and repository, workflow filename
   `publish-pypi.yml`, and environment name `pypi`. For a pending publisher,
   use project name `OfflineCurrencyCoverter` (the name must be available).
4. Keep the fetcher's optional `CMC_API_KEY` in repository **Settings → Secrets
   and variables → Actions → New repository secret**. It is used during fetching;
   the PyPI publishing job does not receive it.
5. Open **Actions → Publish Python package to PyPI → Run workflow**, selecting
   the default branch.

GitHub supplies a short-lived identity token to PyPI during publishing. No
`PYPI_API_TOKEN` secret is needed. A second publication of the same date version
fails because PyPI releases cannot be overwritten. Artifacts remain downloadable
from the successful build job for seven days even if publishing fails.

If your repository name or package name differs from the examples, use your
actual repository in the PyPI publisher settings and update `pyproject.toml`
and the workflow's project URL if you rename the distribution.
