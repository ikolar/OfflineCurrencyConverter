"""ECB fiat and CoinMarketCap cryptocurrency reference rates."""
from importlib import import_module

from .conversion import (
    ConversionError,
    Converter,
    CurrencyBounds,
    CurrencyConverter,
    RateNotFoundError,
    RateQuote,
    UnknownCurrencyError,
    convert,
    get_rate,
    supported_currencies,
)

__all__ = [
    "Asset",
    "ConversionError",
    "Converter",
    "CurrencyBounds",
    "CurrencyConverter",
    "RateNotFoundError",
    "RateQuote",
    "UnknownCurrencyError",
    "add_asset",
    "convert",
    "generate_rates",
    "get_rate",
    "supported_currencies",
]
from ._version import __version__ as __version__


def __getattr__(name):
    """Load generation tools only when explicitly requested."""
    modules = {"Asset": ".core", "generate_rates": ".core", "add_asset": ".assets"}
    if name not in modules:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(modules[name], __name__), name)
    globals()[name] = value
    return value
