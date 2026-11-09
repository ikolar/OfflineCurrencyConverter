"""Snapshot exports preserve raw rates and work offline through API and CLI."""
import shutil
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from offline_currency_converter import CurrencyConverter, export_rates
from offline_currency_converter.cli import main


class ExportTests(unittest.TestCase):
    def test_exact_file_and_stdout_exports_offline(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'eurofxref_and_crypto_rates.2026.11.09.csv'
            data = b'Date,USD,BTC\r\n2026-11-08,,ERROR\r\n2026-11-07,1.123456789,0.000012345678901234\r\n'
            source.write_bytes(data)
            with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
                converter = CurrencyConverter(source)
                output = StringIO()
                with redirect_stdout(output):
                    self.assertIsNone(converter.export_rates())
                self.assertEqual(output.getvalue(), data.decode())
                destination = root / 'export.csv'
                destination.write_text('old contents')
                self.assertEqual(export_rates(destination, output_dir=root), destination)
                self.assertEqual(destination.read_bytes(), data)
                with redirect_stdout(StringIO()) as output:
                    self.assertEqual(main(['export-rates', '--rates-path', str(source)]), 0)
                self.assertEqual(output.getvalue(), data.decode())
                self.assertEqual(main(['export-rates', str(destination), '--rates-path', str(source)]), 0)
                self.assertEqual(destination.read_bytes(), data)
                with self.assertRaises(shutil.SameFileError):
                    converter.export_rates(source)
                self.assertEqual(source.read_bytes(), data)
                with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                    main(['export-rates', str(root / 'absent' / 'file.csv'), '--rates-path', str(source)])
                self.assertEqual(error.exception.code, 2)

    def test_bundled_snapshot_export(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'data'
            data.mkdir()
            source = data / 'eurofxref_and_crypto_rates.2026.11.09.csv'
            source.write_text('Date,USD\n2026-11-08,2\n')
            with patch('offline_currency_converter.conversion.__file__', str(root / 'conversion.py')), patch('offline_currency_converter.conversion.OUTPUT_DIR', root / 'absent'), redirect_stdout(StringIO()) as output:
                export_rates()
            self.assertEqual(output.getvalue(), source.read_text())
