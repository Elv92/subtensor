"""Unit-safe coercion for intent money fields.

An intent money field is denominated in a fixed unit set by the operation: a
``*_tao`` field is TAO (netuid 0), an ``*_alpha`` field is that subnet's alpha.
Callers pass either a plain number (interpreted in that fixed unit) or a
:class:`Balance`, which is validated against the expected netuid and rejected on
mismatch. Either way the wrong unit cannot enter the one write path.
"""

from __future__ import annotations

from ..balance import Balance, UnitMismatchError
from ..result import BittensorError


def _amount(value: "float | int | Balance", netuid: int, label: str) -> float:
    if isinstance(value, Balance):
        if value.netuid != netuid:
            raise UnitMismatchError(
                f"{label} expects a Balance tagged netuid {netuid} "
                f"({'TAO' if netuid == 0 else 'alpha'}), got netuid {value.netuid}."
            )
        amount = value.tao
    else:
        amount = float(value)
    if amount < 0:
        raise BittensorError(f"{label} must be non-negative, got {amount}.")
    return amount


def tao_amount(value: "float | int | Balance") -> float:
    """Coerce a TAO amount (number or netuid-0 Balance) to float TAO."""
    return _amount(value, 0, "TAO amount")


def alpha_amount(value: "float | int | Balance", netuid: int) -> float:
    """Coerce an alpha amount (number or netuid-matched Balance) to float alpha."""
    return _amount(value, netuid, f"alpha amount for netuid {netuid}")
