"""Compatibility wrapper; implementation lives in crypto_exchangerate.assets."""
import sys
from crypto_exchangerate import assets as _implementation

if __name__ == "__main__":
    raise SystemExit(_implementation.main())
else:
    sys.modules[__name__] = _implementation
