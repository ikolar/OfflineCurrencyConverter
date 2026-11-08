"""Public offline rate quotes, provenance, and Decimal conversion contract."""
import unittest
from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import test_conversion
from crypto_exchangerate import (
    Converter,
    RateNotFoundError,
    RateQuote,
    UnknownCurrencyError,
    convert,
    get_rate,
)


class RateQuoteTests(unittest.TestCase):
    setUp = test_conversion.ConversionTests.setUp

    def test_directions_cross_and_provenance(self):
        btc = self.converter.get_rate('BTC', 'EUR', '2026-01-01', 0)
        self.assertEqual(btc, RateQuote(Decimal(100000), date(2026, 1, 1), '2026.01.05'))
        self.assertEqual(self.converter.get_rate('EUR', 'BTC', '2026-01-01', 0).rate, Decimal('0.00001'))
        cross = self.converter.get_rate('JPY', 'USD', '2026-01-04', 1)
        self.assertEqual(cross.rate, Decimal('0.02'))
        self.assertEqual(cross.rate_date, date(2026, 1, 3))
        with self.assertRaises(FrozenInstanceError):
            btc.rate = Decimal(2)

    def test_nearest_and_inclusive_30_days(self):
        for requested, window, selected in [('2026-01-02', 1, 1), ('2025-12-31', 1, 1), ('2026-01-04', 1, 3)]:
            self.assertEqual(self.converter.get_rate('USD', 'EUR', requested, window).rate_date.day, selected)
        for requested in ['2025-12-02', '2026-02-02']:
            self.converter.get_rate('USD', 'EUR', requested, 30)
        for requested in ['2025-12-01', '2026-02-03']:
            with self.assertRaises(RateNotFoundError):
                self.converter.get_rate('USD', 'EUR', requested, 30)

    def test_bad_rates_and_different_rows(self):
        for value in ['', 'ERROR', '0', '-1', 'NaN', 'Infinity', '-Infinity']:
            with self.subTest(value=value):
                self.path.write_text(f'Date,USD,JPY\n2026-01-01,{value},100\n2026-01-02,2,\n')
                converter = Converter(self.path)
                with self.assertRaises(RateNotFoundError):
                    converter.get_rate('USD', 'EUR', '2026-01-01', 0)
                with self.assertRaises(RateNotFoundError):
                    converter.get_rate('USD', 'JPY', '2026-01-01', 1)

    def test_validation_and_identity_quote(self):
        for window in [-1, True, 1.5, None]:
            with self.assertRaises(ValueError):
                self.converter.get_rate('USD', 'USD', '2026-01-01', window)
        for invalid in ['bad', '2026-02-30', 123]:
            with self.assertRaises(ValueError):
                self.converter.get_rate('USD', 'USD', invalid)
        for invalid in ['XYZ', None, 123, '']:
            with self.assertRaises(UnknownCurrencyError):
                self.converter.get_rate(invalid, invalid)
        self.assertEqual(self.converter.get_rate('sit', ' SIT ', '2000-01-01', 0),
                         RateQuote(Decimal(1), date(2000, 1, 1), '2026.01.05'))
        with patch('crypto_exchangerate.conversion._today', return_value=date(2026, 1, 4)):
            self.assertEqual(self.converter.get_rate('EUR', 'EUR').rate_date, date(2026, 1, 3))
            self.assertEqual(self.converter.get_rate('EUR', 'EUR', None).rate_date, date(2026, 1, 4))

    def test_filenames_and_bundled_data(self):
        for name, expected in [('custom.csv', None), ('eurofxref_and_crypto_rates.2026.99.99.csv', None),
                               ('eurofxref_and_crypto_rates.2026.01.05.csv', '2026.01.05')]:
            path = Path(self.temp.name) / name
            path.write_text('Date,USD\n2026-01-01,2\n')
            self.assertEqual(Converter(path).snapshot_version, expected)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / 'data'
            data.mkdir()
            path = data / self.path.name
            path.write_bytes(self.path.read_bytes())
            with patch('crypto_exchangerate.conversion.__file__', str(root / 'conversion.py')), patch('crypto_exchangerate.conversion.OUTPUT_DIR', root / 'absent'):
                self.assertEqual(get_rate('USD', 'EUR', '2026-01-01', 0).snapshot_version, '2026.01.05')

    def test_convert_uses_exactly_one_quote_and_offline(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')), patch('requests.sessions.Session.request', side_effect=AssertionError('Network forbidden')):
            quote = get_rate('USD', 'EUR', '2026-01-01', 0, rates_path=self.path)
            self.assertEqual(convert('123.45', 'USD', 'EUR', '2026-01-01', 0, rates_path=self.path), Decimal('123.45') * quote.rate)
            self.assertEqual(get_rate('USD', 'EUR', '2026-01-01', 0, output_dir=self.temp.name), quote)
            with localcontext() as context:
                context.prec = 8
                quote = RateQuote(Decimal(1) / Decimal(3), date(2026, 1, 1), None)
                with patch.object(self.converter, 'get_rate', return_value=quote) as lookup:
                    self.assertEqual(self.converter.convert('7.12345', 'USD', 'EUR', '2026-01-01', 30), Decimal('7.12345') * quote.rate)
                    lookup.assert_called_once_with('USD', 'EUR', '2026-01-01', 30)
