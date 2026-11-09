"""Shared snapshot settings without data-generation dependencies."""
from pathlib import Path
from zoneinfo import ZoneInfo

OUTPUT_PREFIX = "eurofxref_and_crypto_rates"
OUTPUT_DIR = Path("output")
LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
