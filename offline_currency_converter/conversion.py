"""Convert amounts using the latest local cumulative rate snapshot."""
from __future__ import annotations

import csv
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import NamedTuple

from ._constants import LOCAL_TZ, OUTPUT_DIR, OUTPUT_PREFIX

_DEFAULT_DATE = object()
DEFAULT_DATE_WINDOW = 10


class CurrencyBounds(NamedTuple):
    """First and last dates with a usable rate for a currency."""

    first_date: date
    last_date: date


@dataclass(frozen=True)
class RateQuote:
    """Destination units per source unit, with observation and snapshot dates."""

    rate: Decimal
    rate_date: date
    snapshot_version: str | None


class ConversionError(ValueError):
    """Base class for conversion failures."""


class UnknownCurrencyError(ConversionError):
    """The snapshot has no column for the requested currency."""


class RateNotFoundError(ConversionError):
    """No usable rate exists within the requested date window."""


def _today() -> date:
    return datetime.now(LOCAL_TZ).date()


def _date(value) -> date:
    if value is _DEFAULT_DATE:
        return _today() - timedelta(days=1)
    if value is None:
        return _today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass
    raise ValueError("transaction_date must be a date, datetime, YYYY-MM-DD or D.M.YYYY string, or None")


def _rate(value: str) -> Decimal | None:
    try:
        number = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() and number > 0 else None


class Converter:
    """Load one snapshot for repeated conversions without rereading the file.

    Rates are units per EUR. Cross-conversions require both rates on the same
    date. Equally distant dates prefer the earlier observation.
    """

    def __init__(self, rates_path: str | Path | None = None, *, output_dir: str | Path | None = None):
        if rates_path is None:
            pattern = re.compile(rf"{re.escape(OUTPUT_PREFIX)}\.(\d{{4}}\.\d{{2}}\.\d{{2}})\.csv")
            directories = [Path(output_dir)] if output_dir is not None else [OUTPUT_DIR, Path(__file__).parent / "data"]
            candidates = [p for directory in directories for p in directory.glob(f"{OUTPUT_PREFIX}.*.csv") if pattern.fullmatch(p.name)]
            if not candidates:
                raise RateNotFoundError(f"No rate snapshot found in {output_dir}; generate or download a snapshot first")
            rates_path = max(candidates, key=lambda p: p.name)
        self.rates_path = Path(rates_path)
        match = re.fullmatch(
            rf"{re.escape(OUTPUT_PREFIX)}\.(\d{{4}}\.\d{{2}}\.\d{{2}})\.csv",
            self.rates_path.name,
        )
        self.snapshot_version = None
        if match:
            try:
                date.fromisoformat(match.group(1).replace(".", "-"))
            except ValueError:
                pass
            else:
                self.snapshot_version = match.group(1)
        with self.rates_path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or "Date" not in reader.fieldnames:
                raise ConversionError("Rate snapshot must contain a Date column")
            self.currencies = frozenset(reader.fieldnames) - {"Date"} | {"EUR"}
            self._rows = [(date.fromisoformat(row["Date"]), row) for row in reader]

    def export_rates(self, destination: str | Path | None = None) -> Path | None:
        """Copy the selected CSV to a file, or write it to stdout by default.

        File exports preserve the original bytes and overwrite an existing
        destination. No data is fetched or regenerated.
        """
        if destination is None:
            with self.rates_path.open(encoding="utf-8", newline="") as source:
                shutil.copyfileobj(source, sys.stdout)
            return None
        destination = Path(destination)
        shutil.copyfile(self.rates_path, destination)
        return destination

    @property
    def bounds(self) -> dict[str, CurrencyBounds]:
        """Usable date bounds; currencies with no valid observations are omitted.

        EUR bounds cover the snapshot calendar, although EUR identity quotes
        are valid independently of historical observations.
        """
        bounds = {}
        for day, row in self._rows:
            for currency in self.currencies:
                if currency != "EUR" and _rate(row.get(currency, "")) is None:
                    continue
                previous = bounds.get(currency)
                bounds[currency] = CurrencyBounds(
                    min(day, previous.first_date) if previous else day,
                    max(day, previous.last_date) if previous else day,
                )
        return bounds

    def get_rate(self, from_currency: str, to_currency: str,
                 transaction_date=_DEFAULT_DATE,
                 date_window: int = DEFAULT_DATE_WINDOW) -> RateQuote:
        """Return an offline multiplier and actual observation date within +/-window."""
        if isinstance(date_window, bool) or not isinstance(date_window, int) or date_window < 0:
            raise ValueError("date_window must be a non-negative integer")
        target_date = _date(transaction_date)
        currencies = []
        for currency in (from_currency, to_currency):
            if not isinstance(currency, str) or currency.strip().upper() not in self.currencies:
                raise UnknownCurrencyError(f"Unknown currency: {currency!r}")
            currencies.append(currency.strip().upper())
        source, target = currencies
        if source == target:
            return RateQuote(Decimal(1), target_date, self.snapshot_version)
        return self._lookup_quote(source, target, target_date, date_window)

    def _lookup_quote(self, source, target, target_date, date_window, *, last_known=False):
        currencies = (source, target)
        candidates = sorted(
            ((day, row) for day, row in self._rows
             if (date_window is None or abs((day - target_date).days) <= date_window)
             and (not last_known or day <= target_date)),
            key=lambda item: (abs((item[0] - target_date).days), item[0]),
        )
        available = set()
        for day, row in candidates:
            rates = {c: Decimal(1) if c == "EUR" else _rate(row.get(c, "")) for c in currencies}
            available.update(c for c, rate in rates.items() if rate is not None)
            if all(rate is not None for rate in rates.values()):
                return RateQuote(rates[target] / rates[source], day, self.snapshot_version)
        missing = [c for c in dict.fromkeys(currencies) if c != "EUR" and c not in available]
        detail = f" for {', '.join(missing)}" if missing else f" on a common date for {source} and {target}"
        window = f"within +/-{date_window} days of" if date_window is not None else "on or before"
        raise RateNotFoundError(f"Cannot get a rate{detail} {window} {target_date}")


    def convert(self, amount, from_currency: str, to_currency: str,
                transaction_date=_DEFAULT_DATE, date_window: int = DEFAULT_DATE_WINDOW) -> Decimal:
        """Multiply a validated Decimal amount by one quote, without currency rounding."""
        quote = self.get_rate(from_currency, to_currency, transaction_date, date_window)
        try:
            number = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise ValueError("amount must be a finite number") from None
        if not number.is_finite():
            raise ValueError("amount must be a finite number")
        return number * quote.rate


class CurrencyConverter(Converter):
    """CurrencyConverter-style API backed exclusively by local snapshot data.

    Omitted dates use the latest common observation. An explicit date_window
    selects nearest observations; otherwise missing dates fail unless the
    last-known fallback is enabled. Set decimal=True for Decimal amounts.
    """

    def __init__(self, currency_file: str | Path | None = None,
                 fallback_on_wrong_date=False, fallback_on_missing_rate=False,
                 fallback_on_missing_rate_method="last_known", *, decimal=False,
                 output_dir: str | Path | None = None):
        if fallback_on_missing_rate_method != "last_known":
            raise ValueError("Only last_known fallback is supported; interpolation is not enabled")
        self.fallback_on_wrong_date = fallback_on_wrong_date
        self.fallback_on_missing_rate = fallback_on_missing_rate
        self.fallback_on_missing_rate_method = fallback_on_missing_rate_method
        self.decimal = decimal
        super().__init__(currency_file, output_dir=output_dir)

    def convert(self, amount, currency: str, new_currency: str = "EUR",
                date=None, date_window=None) -> Decimal | float:
        """Convert to EUR by default; decimal=True preserves Decimal results."""
        result = super().convert(amount, currency, new_currency, date, date_window)
        return result if self.decimal else float(result)

    def get_rate(self, currency: str, new_currency: str = "EUR",
                 date=None, date_window=None) -> RateQuote:
        """Return a Decimal quote; date_window overrides the fallback policies."""
        latest = date is None
        if latest:
            # A snapshot calendar may contain weekends with no fiat rates.
            date = max((day for day, _ in self._rows), default=_today())
        requested = _date(date)
        if date_window is not None:
            return super().get_rate(currency, new_currency, requested, date_window)
        try:
            return super().get_rate(currency, new_currency, requested, 0)
        except RateNotFoundError:
            # super() has already validated the symbols and requested date.
            source, target = currency.strip().upper(), new_currency.strip().upper()
            if latest:
                return self._lookup_quote(source, target, requested, None, last_known=True)
            bounds = self.bounds
            available = [bounds[c] for c in (source, target) if c != "EUR" and c in bounds]
            if len(available) != sum(c != "EUR" for c in (source, target)):
                raise
            first = max(bound.first_date for bound in available)
            last = min(bound.last_date for bound in available)
            outside = requested < first or requested > last
            if outside:
                if not self.fallback_on_wrong_date:
                    raise
                # Clamp to the first or last common usable row, never fabricate rates.
                boundary = first if requested < first else last
                return self._lookup_quote(source, target, boundary, None,
                                          last_known=requested > last)
            if not self.fallback_on_missing_rate:
                raise
            return self._lookup_quote(source, target, requested, None, last_known=True)


def get_rate(from_currency: str, to_currency: str,
             transaction_date=_DEFAULT_DATE, date_window: int = DEFAULT_DATE_WINDOW,
             *, rates_path: str | Path | None = None,
             output_dir: str | Path | None = None) -> RateQuote:
    """Look up destination units per source unit from local or bundled data."""
    return Converter(rates_path, output_dir=output_dir).get_rate(
        from_currency, to_currency, transaction_date, date_window,
    )


def convert(amount, from_currency: str, to_currency: str,
            transaction_date=_DEFAULT_DATE, date_window: int = DEFAULT_DATE_WINDOW,
            *, rates_path: str | Path | None = None, output_dir: str | Path | None = None) -> Decimal:
    """Convert using the latest local snapshot, or an explicit CSV rates_path."""
    return Converter(rates_path, output_dir=output_dir).convert(
        amount, from_currency, to_currency, transaction_date, date_window,
    )


def supported_currencies(*, rates_path: str | Path | None = None,
                         output_dir: str | Path | None = None) -> list[str]:
    """Return sorted snapshot symbols, including EUR; dates may have rate gaps."""
    return sorted(Converter(rates_path, output_dir=output_dir).currencies)


def export_rates(destination: str | Path | None = None, *,
                 rates_path: str | Path | None = None,
                 output_dir: str | Path | None = None) -> Path | None:
    """Export the selected local or bundled snapshot to stdout or a CSV file."""
    return Converter(rates_path, output_dir=output_dir).export_rates(destination)
