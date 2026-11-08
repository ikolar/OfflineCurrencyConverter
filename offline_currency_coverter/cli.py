"""Command-line interface for rate generation."""
import argparse
import sys
from pathlib import Path

from . import core
from .conversion import CurrencyConverter


def conversion_main(argv) -> int:
    parser = argparse.ArgumentParser(prog="offline-currency-coverter")
    commands = parser.add_subparsers(dest="command", required=True)
    conversion = commands.add_parser("convert", help="Convert using local or bundled rates (offline)")
    conversion.add_argument("amount")
    conversion.add_argument("from_currency")
    conversion.add_argument("to_currency", nargs="?")
    conversion.add_argument("--to", dest="target", help="Destination currency (default: EUR)")
    conversion.add_argument("--date", help="Transaction date; defaults to the latest common observation")
    conversion.add_argument("--date-window", type=int, default=None)
    currencies = commands.add_parser("currencies", help="List snapshot symbols, including EUR")
    for command in (conversion, currencies):
        source = command.add_mutually_exclusive_group()
        source.add_argument("--rates-path", type=Path)
        source.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        converter = CurrencyConverter(args.rates_path, output_dir=args.output_dir, decimal=True)
        if args.command == "currencies":
            print("\n".join(sorted(converter.currencies)))
        else:
            kwargs = {"date_window": args.date_window}
            if args.date is not None:
                kwargs["date"] = args.date
            if args.target and args.to_currency:
                parser.error("Use either a positional destination or --to, not both")
            target = args.target or args.to_currency or "EUR"
            print(converter.convert(args.amount, args.from_currency, target, **kwargs))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Also accept the CurrencyConverter-style shorthand: 100 USD --to EUR.
    if argv and not argv[0].startswith("--") and argv[0] not in {"convert", "currencies", "-h"}:
        return conversion_main(["convert", *argv])
    if argv and argv[0] in {"convert", "currencies"}:
        return conversion_main(argv)
    parser = argparse.ArgumentParser(epilog="Offline commands: convert AMOUNT FROM TO [--date YYYY-MM-DD]; currencies. Use COMMAND --help for options.")
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
