#!/usr/bin/env python3
"""Build a dated distribution with the latest CSV; optionally publish to PyPI."""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
PREFIX = "eurofxref_and_crypto_rates"


def latest_snapshot(output_dir: Path) -> Path:
    candidates = []
    for path in output_dir.glob(f"{PREFIX}.*.csv"):
        match = re.fullmatch(rf"{PREFIX}\.(\d{{4}})\.(\d{{2}})\.(\d{{2}})\.csv", path.name)
        if match and path.is_file():
            try:
                day = date(*map(int, match.groups()))
            except ValueError:
                continue
            candidates.append((day, path))
    if not candidates:
        raise FileNotFoundError(f"No dated CSV snapshot found in {output_dir}")
    return max(candidates)[1]


def stage_package(destination: Path, snapshot: Path, release_date: date) -> str:
    version = release_date.strftime("%Y.%m.%d")
    package = destination / "crypto_exchangerate"
    shutil.copytree(ROOT / "crypto_exchangerate", package,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "data"))
    (package / "data").mkdir()
    shutil.copy2(snapshot, package / "data" / snapshot.name)
    (package / "_version.py").write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    metadata = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    metadata = metadata.replace('version = "0.1.0"', f'version = "{version}"', 1)
    (destination / "pyproject.toml").write_text(metadata, encoding="utf-8")
    shutil.copy2(ROOT / "README.md", destination / "README.md")
    return version


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true", help="Upload checked artifacts to PyPI")
    parser.add_argument("--no-isolation", action="store_true", help="Use already installed build tooling instead of an isolated environment")
    parser.add_argument("--repository", choices=["pypi", "testpypi"], default="pypi")
    parser.add_argument("--date", type=date.fromisoformat, help="Release date YYYY-MM-DD; defaults to today in Europe/Amsterdam")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output", help="Directory containing rate CSV snapshots")
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    release_date = args.date or datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    destination = args.dist_dir.resolve() / release_date.strftime("%Y.%m.%d")
    # Never upload old artifacts or accidentally replace a prior build.
    if destination.exists():
        parser.error(f"Build directory already exists: {destination}; use a fresh --dist-dir")
    # Fetching is mandatory: never silently package an old snapshot after failure.
    fetch_date = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    subprocess.run([
        sys.executable, "-m", "crypto_exchangerate", "--output-dir", str(args.output_dir.resolve()),
        "--run-date", fetch_date.isoformat(),
    ], cwd=ROOT, check=True)
    snapshot = latest_snapshot(args.output_dir.resolve())
    expected_name = f"{PREFIX}.{fetch_date.strftime('%Y.%m.%d')}.csv"
    if snapshot.name != expected_name:
        raise RuntimeError(f"Fetcher did not produce today's snapshot: {expected_name}")
    # The fetcher can finish successfully while recording individual download
    # failures as ERROR cells. Those are failed refreshes for release purposes.
    with snapshot.open(newline="", encoding="utf-8-sig") as stream:
        if any(value.strip() == "ERROR" for row in csv.reader(stream) for value in row):
            raise RuntimeError(f"Fetcher recorded download errors in {snapshot}; release aborted")
    with TemporaryDirectory(prefix="crypto-exchangerate-release-") as directory:
        stage = Path(directory)
        version = stage_package(stage, snapshot, release_date)
        print(f"Building crypto-exchangerate {version} with {snapshot.name}", flush=True)
        build_args = ["--no-isolation"] if args.no_isolation else []
        subprocess.run([sys.executable, "-m", "build", *build_args, "--outdir", str(destination), str(stage)], check=True)
    artifacts = sorted(destination.glob("*.whl")) + sorted(destination.glob("*.tar.gz"))
    if len(artifacts) != 2:
        raise RuntimeError("Expected exactly one wheel and one source distribution")
    subprocess.run([sys.executable, "-m", "twine", "check", "--strict", *map(str, artifacts)], check=True)
    if args.publish:
        subprocess.run([sys.executable, "-m", "twine", "upload", "--non-interactive",
                        "--repository", args.repository, *map(str, artifacts)], check=True)
    else:
        print(f"Checked artifacts: {destination}. Pass --publish with a fresh --dist-dir to upload.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
