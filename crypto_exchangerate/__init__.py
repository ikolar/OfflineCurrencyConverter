"""ECB fiat and CoinMarketCap cryptocurrency reference rates."""
from .assets import add_asset
from .conversion import (
    ConversionError,
    Converter,
    RateNotFoundError,
    RateQuote,
    UnknownCurrencyError,
    convert,
    get_rate,
    supported_currencies,
)
from .core import Asset, generate_rates

__all__ = [
    "Asset",
    "ConversionError",
    "Converter",
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
