# OfflineCurrencyCoverter

Historical fiat and cryptocurrency conversion for offline Python applications.
Requires Python 3.10 or newer.

OfflineCurrencyCoverter follows the familiar
[CurrencyConverter API](https://github.com/alexprengere/currencyconverter),
including `CurrencyConverter`, `convert()`, `date=`, currency bounds, and
optional fallback settings. It extends this interface with cryptocurrency
coverage, configurable date windows, and exchange-rate quotes with snapshot
metadata. See [API compatibility](#api-compatibility) for supported behavior.

**Exchange-rate data is included in every package.** Automated daily builds
refresh the bundled historical dataset and produce a date-versioned wheel.
Applications receive updated rates by installing a newer package build;
conversion and rate lookup never require access to external data services.
This supports air-gapped deployments using an internal Python package index
or a local wheelhouse.

## Currency data

Fiat reference rates come from the European Central Bank. Cryptocurrency and
stablecoin rates come from CoinMarketCap. All source rates are stored as units
per EUR, enabling conversion between supported currencies through EUR.

Each wheel contains one cumulative CSV snapshot. Its calendar starts on
1999-01-04 and ends on the day before the snapshot's run date. Individual
currencies have different periods of coverage. Crypto uses completed daily
closing prices; unfinished current-day observations are excluded.

A scheduled GitHub Action generates updated data and a wheel daily at
16:30 Europe/Amsterdam. Successful builds are committed to [`output/`](output/)
and made available as workflow artifacts. Versions follow the snapshot date:
`2026.11.9` identifies the November 9, 2026 snapshot. Publication to public PyPI
is a separate, manually triggered workflow.

Fiat observations may be absent on weekends and holidays. Missing or failed
source observations remain unavailable until a subsequent update obtains them.
The installed dataset stays fixed until the package or local snapshot is
replaced; the converter does not refresh it automatically.

## Installation

Download a wheel from [`output/`](output/), then install it in a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install /path/to/offlinecurrencycoverter-2026.11.9-py3-none-any.whl
```

For air-gapped systems, make the wheel and its dependencies available through
an internal PyPI mirror or a local wheelhouse. For example:

```sh
python -m pip install --no-index --find-links=/path/to/wheelhouse OfflineCurrencyCoverter
```

The wheel bundles the rates, but its dependencies must also be installed.
To replace an installed build with an updated wheel of the same version, use
`python -m pip install --force-reinstall /path/to/package.whl`.

## Python API

Create a converter once and reuse it:

```python
from offline_currency_coverter import CurrencyConverter

c = CurrencyConverter()
euros = c.convert(100, "USD")          # EUR is the default destination.
yen = c.convert(100, "USD", "JPY")    # Latest common observation.
```

Choose a historical date with `date=`:

```python
from datetime import date

amount = c.convert(100, "USD", "EUR", date=date(2026, 11, 2))
```

Omitting `date`, or passing `None`, uses the latest common observation in the
loaded snapshot. An explicit date requires an exact observation unless a date
window or fallback is enabled. Dates also accept `datetime` objects,
`YYYY-MM-DD` strings, and `D.M.YYYY` strings.

### Decimal amounts and rounding

Conversions return floats by default. Enable `decimal=True` for `Decimal`
results, and pass string or `Decimal` amounts to preserve input precision:

```python
from decimal import Decimal, ROUND_HALF_UP
from offline_currency_coverter import CurrencyConverter

c = CurrencyConverter(decimal=True)
eur = c.convert("100", "USD", date="2026-11-02")
eur = eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
```

The converter does not apply monetary rounding. Round the final amount to the
destination currency's minor unit: EUR and USD use two decimal places, while
some currencies use zero or three. Formatting with `f"{eur:.2f}"` changes only
the displayed text; `quantize()` returns a rounded `Decimal` value.

### Date windows

Pass `date_window` to select the nearest usable observation within an inclusive
window of calendar days before or after the requested date:

```python
amount = c.convert("100", "USD", "EUR", date="2026-11-02", date_window=30)
```

An equally distant pair of observations resolves to the earlier date. Both
currencies must have valid rates on the same observation date. Zero requires
an exact match. An explicit window overrides fallback settings, including
out-of-range fallback, and raises `RateNotFoundError` if no match exists.

Applications requiring a 30-day policy must explicitly pass their selected
`date` and `date_window=30`.

### Fallbacks

Enable last-known fallback for missing dates within the currencies' date bounds:

```python
c = CurrencyConverter(fallback_on_missing_rate=True, decimal=True)
```

Enable boundary fallback for requested dates outside the available range:

```python
c = CurrencyConverter(
    fallback_on_missing_rate=True,
    fallback_on_wrong_date=True,
    decimal=True,
)
```

Last-known fallback selects a common observation on or before the requested
date. Boundary fallback uses the first or last common available observation.
The supported method is `fallback_on_missing_rate_method="last_known"`;
linear interpolation is not implemented. All quotes identify actual observations.

### Rate quotes

`get_rate()` returns an immutable `RateQuote` containing:

| Field | Meaning |
| --- | --- |
| `rate` | `Decimal` multiplier: destination units per one source unit |
| `rate_date` | Actual selected observation date, as `datetime.date` |
| `snapshot_version` | Snapshot filename date, such as `"2026.11.09"`; `None` for unrecognized custom filenames |

```python
from decimal import Decimal

quote = c.get_rate("USD", "EUR", date="2026-11-02", date_window=30)
euro_amount = Decimal("100") * quote.rate
print(quote.rate_date, quote.snapshot_version)
```

The multiplier is destination-units-per-EUR divided by source-units-per-EUR.
EUR has an implicit rate of 1. For identical supported currencies, the rate is
1 and `rate_date` is the resolved requested date, without requiring a historical
observation. The snapshot version describes the dataset, not per-observation
source provenance.

### Supported currencies and date bounds

```python
print(sorted(c.currencies))
first_date, last_date = c.bounds["USD"]
print(first_date, last_date)
```

`currencies` includes EUR, fiat, crypto, and historical currency symbols present
in the snapshot. A listed currency may have no rate for a particular date.
`bounds` includes only currencies with usable observations. EUR bounds cover
the snapshot calendar, although EUR identity conversions also work outside it.

### Custom data

Load an explicit local CSV, using the same units-per-EUR format:

```python
c = CurrencyConverter("/path/to/snapshot.csv", decimal=True)
# Also accepted: CurrencyConverter(currency_file="/path/to/snapshot.csv")
```

By default, the newest filename-dated snapshot is selected across local
`output/` and the package's bundled data. `output_dir=` restricts selection to
a chosen directory. URL and ZIP inputs are not supported.

### Exceptions

- `UnknownCurrencyError`: a requested symbol is not supported by the snapshot.
- `RateNotFoundError`: no snapshot or suitable observation is available.
- `ValueError`: invalid amounts, dates, date windows, or unsupported fallback options.

Blank, `ERROR`, zero, negative, and non-finite rates are never used for conversion.

## Command line

```sh
offline-currency-coverter 100 USD --to EUR
offline-currency-coverter 100 USD --to EUR --date 2026-11-02 --date-window 30
offline-currency-coverter currencies
```

The equivalent module command is `python -m offline_currency_coverter` followed
by the same arguments. Use `--rates-path /path/to/snapshot.csv` for an explicit
CSV. Commands use the latest common observation when no date is supplied;
with `--date`, supply `--date-window` if an exact match is not required.
Amounts are printed without monetary rounding.

## API compatibility

This package implements the common CurrencyConverter calling interface with
offline fiat and crypto data. It is not a complete drop-in implementation:
network sources, ZIP inputs, and linear interpolation are not supported. Rates
for cross-currency conversion always come from the same observation date.
`date_window` and `get_rate()` are additional capabilities.

The original `Converter`, module-level `convert()`, and module-level `get_rate()`
remain available. They use `transaction_date=`, default to yesterday in
Europe/Amsterdam, interpret explicit `None` as today, and default to a +/-10-day
window. They always use `Decimal` amounts and rates:

```python
from offline_currency_coverter import get_rate, convert

quote = get_rate("USD", "EUR", transaction_date="2026-11-02", date_window=30)
amount = convert("100", "USD", "EUR", transaction_date="2026-11-02", date_window=30)
```

## Development and data maintenance

See [Data generation and package maintenance](docs/operations.md) for source
configuration, daily scheduling, CSV/Excel formats, caching, wheel builds,
and optional PyPI publication.

```sh
python -m pip install -r requirements.txt -r requirements-release.txt
python -m unittest discover -v
python build_wheel.py
```

`build_wheel.py` packages the newest existing snapshot without downloading data.
`python rates.py` performs the network-enabled data update separately.
