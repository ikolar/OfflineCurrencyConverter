"""Verify release staging and installed-data lookup behavior."""
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from offline_currency_converter import Converter
from publish_package import latest_snapshot, stage_package


class PackagingTests(unittest.TestCase):
    def test_stage_contains_only_latest_snapshot_and_date_version(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'output'
            output.mkdir()
            for name in ['2026.10.29', '2026.11.02', '2026.99.99']:
                (output / f'eurofxref_and_crypto_rates.{name}.csv').write_text('Date,USD\n2026-11-01,2\n')
            selected = latest_snapshot(output)
            self.assertIn('2026.11.02', selected.name)
            stage = root / 'stage'
            stage.mkdir()
            version = stage_package(stage, selected, date(2026, 11, 3))
            self.assertEqual(version, '2026.11.03')
            self.assertEqual([p.name for p in (stage / 'offline_currency_converter/data').iterdir()], [selected.name])
            self.assertIn('version = "2026.11.03"', (stage / 'pyproject.toml').read_text())
            self.assertIn('2026.11.03', (stage / 'offline_currency_converter/_version.py').read_text())

    def test_bundled_fallback_and_newer_local_snapshot(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / 'package'
            data = package / 'data'
            data.mkdir(parents=True)
            local = root / 'local'
            local.mkdir()
            bundled = data / 'eurofxref_and_crypto_rates.2026.11.01.csv'
            bundled.write_text('Date,USD\n2026-10-31,2\n')
            with patch('offline_currency_converter.conversion.__file__', str(package / 'conversion.py')), patch('offline_currency_converter.conversion.OUTPUT_DIR', local):
                self.assertEqual(Converter().rates_path, bundled)
                newer = local / 'eurofxref_and_crypto_rates.2026.11.02.csv'
                newer.write_text('Date,USD\n2026-11-01,3\n')
                self.assertEqual(Converter().rates_path, newer)
                with self.assertRaises(FileNotFoundError):
                    latest_snapshot(root / 'missing')

    def test_failed_fetch_prevents_build_and_upload(self):
        import subprocess
        from publish_package import main
        with TemporaryDirectory() as directory, patch('publish_package.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'fetch')) as run, patch('publish_package.stage_package') as stage:
            with self.assertRaises(subprocess.CalledProcessError):
                main(['--publish', '--dist-dir', directory])
            self.assertEqual(run.call_count, 1)
            self.assertIn('offline_currency_converter', run.call_args.args[0])
            stage.assert_not_called()

    def test_missing_snapshot_or_error_cells_prevent_build(self):
        from publish_package import main
        from datetime import datetime
        from zoneinfo import ZoneInfo
        for failed_output in ['missing', 'errors']:
            with self.subTest(failed_output=failed_output), TemporaryDirectory() as directory:
                root = Path(directory)
                output = root / 'output'
                output.mkdir()
                if failed_output == 'errors':
                    today = datetime.now(ZoneInfo('Europe/Amsterdam')).strftime('%Y.%m.%d')
                    (output / f'eurofxref_and_crypto_rates.{today}.csv').write_text('Date,USD\n2026-11-01,ERROR\n')
                with patch('publish_package.subprocess.run') as run, patch('publish_package.stage_package') as stage:
                    with self.assertRaises((FileNotFoundError, RuntimeError)):
                        main(['--output-dir', str(output), '--dist-dir', str(root / 'dist')])
                    self.assertEqual(run.call_count, 1)
                    stage.assert_not_called()
