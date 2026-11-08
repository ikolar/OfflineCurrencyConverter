"""Compatibility wrapper; implementation lives in offline_currency_coverter.core."""
import sys
from offline_currency_coverter import core as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
