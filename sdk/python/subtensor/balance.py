"""Fixed-point money type.

A ``Balance`` is an integer amount of rao (1 TAO = 1e9 rao) tagged with the
``netuid`` whose currency it denominates. netuid 0 is TAO; any other netuid is
that subnet's alpha. Arithmetic and comparison between two balances of different
netuids raises, so mixing TAO and alpha (or two different subnets' alpha) is a
loud error rather than a silent miscalculation.

All arithmetic is integer arithmetic on rao. Floats only appear at the edges
(``tao`` for display, ``from_tao`` for convenience input).
"""

from __future__ import annotations

from decimal import Decimal

from .settings import ALPHA_SYMBOL, RAO_PER_TAO, TAO_SYMBOL


class UnitMismatchError(TypeError):
    """Raised when combining balances denominated in different currencies."""


class Balance:
    __slots__ = ("rao", "netuid")

    def __init__(self, rao: int, netuid: int = 0):
        self.rao = int(rao)
        self.netuid = netuid

    @classmethod
    def from_rao(cls, rao: int, netuid: int = 0) -> "Balance":
        return cls(int(rao), netuid)

    @classmethod
    def from_tao(cls, tao: "float | str | Decimal", netuid: int = 0) -> "Balance":
        """Create a Balance from a TAO amount.

        Pass a ``str`` or ``Decimal`` for an exact amount (recommended for large
        values): a Python ``float`` literal loses precision above ~9M TAO before
        this is even called, so exactness requires a non-float input.
        """
        return cls(int((Decimal(str(tao)) * RAO_PER_TAO).to_integral_value()), netuid)

    @property
    def tao(self) -> float:
        return self.rao / RAO_PER_TAO

    @property
    def unit(self) -> str:
        return TAO_SYMBOL if self.netuid == 0 else ALPHA_SYMBOL

    def _same_unit(self, other: "Balance") -> None:
        if self.netuid != other.netuid:
            raise UnitMismatchError(
                f"Cannot combine balances of different currencies: "
                f"netuid {self.netuid} and netuid {other.netuid}. "
                "Set both to the same netuid first."
            )

    def __repr__(self) -> str:
        return f"{self.unit}{self.tao:,.9f}"

    __str__ = __repr__

    def __eq__(self, other: object) -> bool:
        # Equality never raises: a different-currency balance is simply not equal,
        # so containment (`x in [...]`) and dict/set membership behave sanely.
        if isinstance(other, Balance):
            return self.netuid == other.netuid and self.rao == other.rao
        if isinstance(other, int):
            return self.rao == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.rao, self.netuid))

    def __lt__(self, other: "Balance | int | float") -> bool:
        return self.rao < self._rao_of(other)

    def __le__(self, other: "Balance | int | float") -> bool:
        return self.rao <= self._rao_of(other)

    def __gt__(self, other: "Balance | int | float") -> bool:
        return self.rao > self._rao_of(other)

    def __ge__(self, other: "Balance | int | float") -> bool:
        return self.rao >= self._rao_of(other)

    def _rao_of(self, other: "Balance | int") -> int:
        if isinstance(other, Balance):
            self._same_unit(other)
            return other.rao
        if isinstance(other, bool):  # bool is an int subclass; reject explicitly
            raise TypeError("Cannot compare Balance with bool")
        if isinstance(other, int):
            return other
        if isinstance(other, float):
            raise TypeError(
                "Compare a Balance against another Balance or an int (rao). "
                "For a TAO amount use tao(x): `balance > tao(0.5)`."
            )
        raise TypeError(f"Cannot compare Balance with {type(other).__name__}")

    def __add__(self, other: "Balance | int") -> "Balance":
        return Balance(self.rao + self._rao_of(other), self.netuid)

    def __sub__(self, other: "Balance | int") -> "Balance":
        return Balance(self.rao - self._rao_of(other), self.netuid)

    def __neg__(self) -> "Balance":
        return Balance(-self.rao, self.netuid)

    def __bool__(self) -> bool:
        return bool(self.rao)


def tao(amount: float, netuid: int = 0) -> Balance:
    return Balance.from_tao(amount, netuid)


def rao(amount: int, netuid: int = 0) -> Balance:
    return Balance.from_rao(amount, netuid)
