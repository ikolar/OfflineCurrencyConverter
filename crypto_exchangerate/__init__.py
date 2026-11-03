"""ECB fiat and CoinMarketCap cryptocurrency reference rates."""
from .core import Asset, generate_rates
from .assets import add_asset
from .conversion import convert, Converter, ConversionError, UnknownCurrencyError, RateNotFoundError

__all__ = ["Asset", "generate_rates", "add_asset", "convert", "Converter",
           "ConversionError", "UnknownCurrencyError", "RateNotFoundError"]
from ._version import __version__
