"""Command-line interface for rate generation."""
import argparse
from pathlib import Path
from . import core


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=core.OUTPUT_DIR)
    parser.add_argument("--ecb-cache-dir", type=Path, default=core.ECB_CACHE_DIR)
    parser.add_argument("--force", action="store_true", help="Redownload ECB ZIPs regardless of cache freshness.")
    parser.add_argument(
        "--run-date",
        help="Override snapshot run date (YYYY-MM-DD); data ends the previous day.",
    )
    parser.add_argument(
        "--ecb-daily-file",
        type=Path,
        help="Use a local unzipped ECB daily CSV instead of downloading it.",
    )
    parser.add_argument(
        "--ecb-hist-file",
        type=Path,
        help="Use a local unzipped ECB historical CSV instead of downloading it.",
    )
    parser.add_argument("--config", type=Path, help="Asset JSON file; defaults to local or bundled assets.json")
    args = parser.parse_args(argv)

    core.generate_rates(
        output_dir=args.output_dir, ecb_cache_dir=args.ecb_cache_dir,
        run_date=args.run_date, ecb_daily_file=args.ecb_daily_file,
        ecb_hist_file=args.ecb_hist_file, force=args.force, config_path=args.config,
    )
    return 0
