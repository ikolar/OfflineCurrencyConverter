"""CurrencyConverter-style facade preserving offline Decimal quote semantics."""
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import test_conversion
from offline_currency_coverter import (
    CurrencyBounds,
    CurrencyConverter,
    RateNotFoundError,
)
from offline_currency_coverter.cli import main


class CurrencyConverterTests(unittest.TestCase):
    setUp = test_conversion.ConversionTests.setUp

    def test_optional_target_and_date_keyword(self):
        converter = CurrencyConverter(currency_file=self.path, decimal=True)
        self.assertEqual(converter.convert('100', 'USD', date=date(2026, 1, 1)), Decimal(50))
        self.assertEqual(converter.convert('100', 'USD', 'JPY', date='2026-01-01'), Decimal(5000))
        quote = converter.get_rate('USD', date='2026-01-01', date_window=0)
        self.assertEqual(quote.rate, Decimal('0.5'))
        self.assertEqual(quote.rate_date, date(2026, 1, 1))
        self.assertEqual(quote.snapshot_version, '2026.01.05')
        self.assertEqual(converter.get_rate('USD', 'JPY', '2026-01-04', 1).rate_date, date(2026, 1, 3))
        self.assertIn('BTC', converter.currencies)
        self.assertEqual(converter.get_rate('USD', 'JPY').rate_date, date(2026, 1, 3))

    def test_bounds_skip_unusable_observations(self):
        converter = CurrencyConverter(self.path, decimal=True)
        bounds = converter.bounds
        self.assertEqual(bounds['USD'], CurrencyBounds(date(2026, 1, 1), date(2026, 1, 3)))
        self.assertEqual(bounds['EUR'], (date(2026, 1, 1), date(2026, 1, 4)))
        self.assertEqual(bounds['BTC'].last_date, date(2026, 1, 3))
        self.assertNotIn('SIT', bounds)

    def test_latest_default_and_explicit_window(self):
        converter = CurrencyConverter(output_dir=self.temp.name, decimal=True)
        with patch('offline_currency_coverter.conversion._today', return_value=date(2026, 1, 4)):
            self.assertEqual(converter.get_rate('EUR').rate_date, date(2026, 1, 4))
            self.assertEqual(converter.get_rate('USD', date=None).rate_date, date(2026, 1, 3))
        with self.assertRaises(RateNotFoundError):
            converter.get_rate('USD', date='2026-02-02')
        self.assertEqual(converter.get_rate('USD', date='2026-02-02', date_window=30).rate_date, date(2026, 1, 3))
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            self.assertEqual(CurrencyConverter(self.path, decimal=True).convert('100', 'USD', date='2026-01-01'), Decimal(50))

    def test_cli_default_target_and_shorthand(self):
        for argv in [['convert', '100', 'USD'], ['100', 'USD', '--to', 'EUR'], ['convert', '100', 'USD', 'EUR']]:
            with self.subTest(argv=argv), redirect_stdout(StringIO()) as output:
                self.assertEqual(main([*argv, '--date', '2026-01-01', '--rates-path', str(self.path)]), 0)
                self.assertEqual(Decimal(output.getvalue().strip()), Decimal(50))
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as failure:
            main(['convert', '100', 'USD', 'JPY', '--to', 'EUR', '--rates-path', str(self.path)])
        self.assertEqual(failure.exception.code, 2)

    def test_last_known_and_outside_bounds_fallbacks(self):
        strict = CurrencyConverter(self.path)
        self.assertIsInstance(strict.convert(100, 'USD'), float)
        with self.assertRaises(RateNotFoundError):
            strict.convert(100, 'USD', date='2026-01-02')
        fallback = CurrencyConverter(self.path, fallback_on_missing_rate=True, decimal=True)
        quote = fallback.get_rate('USD', date='2026-01-02')
        self.assertEqual(quote.rate_date, date(2026, 1, 1))
        self.assertEqual(quote.rate, Decimal('0.5'))
        self.assertEqual(fallback.get_rate('USD', 'JPY', date='2026-01-02').rate_date, date(2026, 1, 1))
        with self.assertRaises(RateNotFoundError):
            fallback.get_rate('USD', date='2026-02-02')
        clamped = CurrencyConverter(self.path, fallback_on_wrong_date=True, decimal=True)
        self.assertEqual(clamped.get_rate('USD', date='2025-01-01').rate_date, date(2026, 1, 1))
        self.assertEqual(clamped.get_rate('USD', date='2027-01-01').rate_date, date(2026, 1, 3))
        with self.assertRaises(RateNotFoundError):
            clamped.get_rate('USD', date='2027-01-01', date_window=30)
        with self.assertRaises(ValueError):
            CurrencyConverter(self.path, fallback_on_missing_rate_method='linear_interpolation')
