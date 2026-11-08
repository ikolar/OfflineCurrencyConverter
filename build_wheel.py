"""Build an offline conversion wheel from an existing dated snapshot, without fetching."""
import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from publish_package import ROOT, latest_snapshot, stage_package


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--no-isolation", action="store_true")
    parser.add_argument("--revision", type=int, default=0, help="Optional post-release revision (default: 0, date-only version)")
    args = parser.parse_args(argv)
    if args.revision < 0:
        parser.error("--revision must be non-negative")
    snapshot = latest_snapshot(args.output_dir.resolve())
    # Version identifies the bundled snapshot, rather than the build machine's date.
    snapshot_date = date.fromisoformat(snapshot.name.removeprefix("eurofxref_and_crypto_rates.").removesuffix(".csv").replace(".", "-"))
    destination = args.dist_dir.resolve() / snapshot_date.strftime("%Y.%m.%d")
    if destination.exists():
        parser.error(f"Build directory already exists: {destination}; use a fresh --dist-dir")
    with TemporaryDirectory(prefix="crypto-exchangerate-wheel-") as directory:
        stage = Path(directory)
        stage_package(stage, snapshot, snapshot_date, revision=args.revision)
        subprocess.run([sys.executable, "-m", "build", "--wheel",
                        *(["--no-isolation"] if args.no_isolation else []),
                        "--outdir", str(destination), str(stage)], check=True)
    wheel, = destination.glob("*.whl")
    subprocess.run([sys.executable, "-m", "twine", "check", "--strict", str(wheel)], check=True)
    print(f"Built {wheel} with {snapshot.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
