"""Convert amounts using the latest local cumulative rate snapshot."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from .core import LOCAL_TZ, OUTPUT_DIR, OUTPUT_PREFIX

_DEFAULT_DATE = object()
DEFAULT_DATE_WINDOW = 10


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
        with self.rates_path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or "Date" not in reader.fieldnames:
                raise ConversionError("Rate snapshot must contain a Date column")
            self.currencies = frozenset(reader.fieldnames) - {"Date"} | {"EUR"}
            self._rows = [(date.fromisoformat(row["Date"]), row) for row in reader]

    def convert(self, amount, from_currency: str, to_currency: str,
                transaction_date=_DEFAULT_DATE, date_window: int = DEFAULT_DATE_WINDOW) -> Decimal:
        """Return a Decimal amount; date_window is inclusive in both directions."""
        if isinstance(date_window, bool) or not isinstance(date_window, int) or date_window < 0:
            raise ValueError("date_window must be a non-negative integer")
        target_date = _date(transaction_date)
        currencies = []
        for currency in (from_currency, to_currency):
            if not isinstance(currency, str) or currency.strip().upper() not in self.currencies:
                raise UnknownCurrencyError(f"Unknown currency: {currency!r}")
            currencies.append(currency.strip().upper())
        source, target = currencies
        try:
            number = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise ValueError("amount must be a finite number") from None
        if not number.is_finite():
            raise ValueError("amount must be a finite number")
        if source == target:
            return number
        candidates = sorted(
            ((day, row) for day, row in self._rows if abs((day - target_date).days) <= date_window),
            key=lambda item: (abs((item[0] - target_date).days), item[0]),
        )
        available = set()
        for day, row in candidates:
            rates = {c: Decimal(1) if c == "EUR" else _rate(row.get(c, "")) for c in currencies}
            available.update(c for c, rate in rates.items() if rate is not None)
            if all(rate is not None for rate in rates.values()):
                return number / rates[source] * rates[target]
        missing = [c for c in dict.fromkeys(currencies) if c != "EUR" and c not in available]
        detail = f" for {', '.join(missing)}" if missing else f" on a common date for {source} and {target}"
        raise RateNotFoundError(f"Cannot get a rate{detail} within +/-{date_window} days of {target_date}")


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
