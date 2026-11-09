"""Offline lookup must not import optional data-generation dependencies."""
import subprocess
import sys
import unittest
from pathlib import Path


class ImportTests(unittest.TestCase):
    def test_offline_import_and_conversion_without_generation_modules(self):
        script = '''
import importlib.abc
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

class BlockGenerationImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'pandas', 'numpy', 'requests', 'openpyxl'} or fullname in {
            'offline_currency_converter.core', 'offline_currency_converter.assets'
        }:
            raise AssertionError(f'Unexpected generation import: {fullname}')

sys.meta_path.insert(0, BlockGenerationImports())
from offline_currency_converter import CurrencyConverter, get_rate
from offline_currency_converter.cli import main
with TemporaryDirectory() as directory:
    path = Path(directory) / 'custom.csv'
    path.write_text('Date,USD\\n2026-11-02,2\\n')
    converter = CurrencyConverter(path, decimal=True)
    assert converter.convert('100', 'USD') == 50
    assert get_rate('USD', 'EUR', '2026-11-02', 0, rates_path=path).rate_date.isoformat() == '2026-11-02'
    assert main(['100', 'USD', '--rates-path', str(path)]) == 0
'''
        result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).parent,
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_generation_exports_still_work(self):
        from offline_currency_converter import Asset, add_asset, generate_rates
        self.assertTrue(callable(Asset))
        self.assertTrue(callable(add_asset))
        self.assertTrue(callable(generate_rates))
