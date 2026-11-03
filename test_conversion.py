"""Conversion lookup, cross rates, and public API behavior."""
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from crypto_exchangerate import Converter, convert, UnknownCurrencyError, RateNotFoundError


class ConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'eurofxref_and_crypto_rates.2026.01.05.csv'
        with self.path.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerows([
                ['Date', 'USD', 'JPY', 'SIT', 'BTC'],
                ['2026-01-04', '', '180', '', 'ERROR'],
                ['2026-01-03', '4', '200', '', '0.00002'],
                ['2026-01-02', 'ERROR', '', '', 'NaN'],
                ['2026-01-01', '2', '100', '', '0.00001'],
            ])
        self.converter = Converter(self.path)

    def test_direct_inverse_and_cross(self):
        for source, target, expected in [('USD', 'EUR', '50'), ('EUR', 'USD', '200'), ('JPY', 'USD', '2')]:
            with self.subTest(source=source, target=target):
                self.assertEqual(self.converter.convert(100, source, target, '1.1.2026', 0), Decimal(expected))
        self.assertEqual(self.converter.convert('0.00001', 'BTC', 'EUR', '2026-01-01', 0), Decimal(1))

    def test_nearest_and_earlier_tie(self):
        self.assertEqual(self.converter.convert(100, 'USD', 'EUR', '2026-01-02', 1), Decimal(50))
        # The nearest JPY row lacks USD; use the closest common date instead.
        self.assertEqual(self.converter.convert(100, 'JPY', 'USD', '2026-01-04', 1), Decimal(2))

    def test_errors_name_unavailable_currency(self):
        with self.assertRaisesRegex(UnknownCurrencyError, 'XYZ'):
            self.converter.convert(1, 'XYZ', 'EUR')
        with self.assertRaisesRegex(UnknownCurrencyError, 'XYZ'):
            self.converter.convert(1, 'EUR', 'XYZ')
        with self.assertRaisesRegex(RateNotFoundError, 'SIT'):
            self.converter.convert(100, 'JPY', 'SIT', '2026-01-01', 10)
        with self.assertRaises(RateNotFoundError):
            self.converter.convert(100, 'USD', 'EUR', '2026-01-02', 0)
        with self.assertRaises(RateNotFoundError):
            self.converter.convert(1, 'BTC', 'EUR', '2026-01-04', 0)

    @patch('crypto_exchangerate.conversion._today', return_value=date(2026, 1, 4))
    def test_omitted_date_yesterday_none_today_and_default_window(self, _):
        self.assertEqual(self.converter.convert(100, 'JPY', 'EUR'), Decimal('0.5'))
        self.assertEqual(self.converter.convert(180, 'JPY', 'EUR', None), Decimal(1))
        self.assertEqual(self.converter.convert(100, 'USD', 'EUR', '2026-01-13'), Decimal(25))
        with self.assertRaises(RateNotFoundError):
            self.converter.convert(100, 'USD', 'EUR', '2026-01-14')

    def test_validation_and_identity(self):
        self.assertEqual(self.converter.convert(100, 'usd', ' USD ', '2020-01-01', 0), Decimal(100))
        for window in [-1, 1.5, True, None]:
            with self.assertRaises(ValueError):
                self.converter.convert(1, 'EUR', 'USD', date_window=window)
        for amount in ['NaN', 'Infinity', 'invalid']:
            with self.assertRaises(ValueError):
                self.converter.convert(amount, 'EUR', 'USD')
        with self.assertRaises(ValueError):
            self.converter.convert(1, 'EUR', 'USD', 'not a date')

    def test_latest_snapshot_and_explicit_path(self):
        self.assertEqual(convert(100, 'USD', 'EUR', '2026-01-01', 0, output_dir=self.temp.name), Decimal(50))
        self.assertEqual(convert(100, 'USD', 'EUR', '2026-01-01', rates_path=self.path), Decimal(50))
        with TemporaryDirectory() as empty:
            with self.assertRaises(RateNotFoundError):
                Converter(output_dir=empty)


if __name__ == '__main__':
    unittest.main()
