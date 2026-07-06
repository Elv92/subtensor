"""Crowdloans: raise funds toward a cap that, on success, funds a target or call.

A creator opens a crowdloan with an initial deposit, cap, and end block, choosing
either a ``target_ss58`` to receive the raised funds or an inner ``call`` to
dispatch (exactly one). Contributors add funds; if the cap is reached the creator
finalizes, otherwise contributors are refunded. Amounts are TAO.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from ..balance import Balance
from .base import BuiltCall, Intent
from .registry import build as build_intent
from .registry import register


def _rao(amount_tao: float) -> int:
    if amount_tao < 0:
        raise ValueError("amount must be non-negative")
    return Balance.from_tao(amount_tao).rao


@register
@dataclass
class CreateCrowdloan(Intent):
    """Open a crowdloan raising up to ``cap_tao`` by ``end`` block.

    Provide exactly one of ``target_ss58`` (address to receive funds) or ``call``
    (``{"op": ..., ...args}`` dispatched with the creator's origin on finalize).
    """

    op = "create_crowdloan"
    signer = "coldkey"
    wraps = (("Crowdloan", "create"),)

    deposit_tao: float
    min_contribution_tao: float
    cap_tao: float
    end: int
    target_ss58: Optional[str] = None
    call: Optional[dict] = None

    def __post_init__(self):
        if bool(self.target_ss58) == bool(self.call):
            raise ValueError("provide exactly one of target_ss58 or call")

    async def build(self, substrate, wallet: Any):
        inner = None
        if self.call:
            args = dict(self.call)
            op = args.pop("op", None)
            if not op:
                raise ValueError("crowdloan 'call' needs an 'op' key")
            built = await build_intent(op, args).build(substrate, wallet)
            inner = built.call if isinstance(built, BuiltCall) else built
        return await substrate.compose(
            calls.Crowdloan.create(
                deposit=_rao(self.deposit_tao),
                min_contribution=_rao(self.min_contribution_tao),
                cap=_rao(self.cap_tao),
                end=self.end,
                call=inner,
                target_address=self.target_ss58,
            )
        )

    def summary(self) -> str:
        return (
            f"create crowdloan (cap {self.cap_tao} TAO, deposit {self.deposit_tao}, end {self.end})"
        )

    def spend_tao(self) -> float:
        return self.deposit_tao


@register
@dataclass
class ContributeCrowdloan(Intent):
    """Contribute TAO to an active crowdloan."""

    op = "contribute_crowdloan"
    signer = "coldkey"
    wraps = (("Crowdloan", "contribute"),)

    crowdloan_id: int
    amount_tao: float

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Crowdloan.contribute(crowdloan_id=self.crowdloan_id, amount=_rao(self.amount_tao))
        )

    def summary(self) -> str:
        return f"contribute {self.amount_tao} TAO to crowdloan {self.crowdloan_id}"

    def spend_tao(self) -> float:
        return self.amount_tao


@dataclass
class _CrowdloanId(Intent):
    """Base for the crowdloan operations that take only an id."""

    crowdloan_id: int


@register
@dataclass
class FinalizeCrowdloan(_CrowdloanId):
    """Finalize a crowdloan that reached its cap (creator only)."""

    op = "finalize_crowdloan"
    signer = "coldkey"
    wraps = (("Crowdloan", "finalize"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.Crowdloan.finalize(crowdloan_id=self.crowdloan_id))

    def summary(self) -> str:
        return f"finalize crowdloan {self.crowdloan_id}"


@register
@dataclass
class RefundCrowdloan(_CrowdloanId):
    """Refund contributors of a non-finalized crowdloan (may need repeating)."""

    op = "refund_crowdloan"
    signer = "coldkey"
    wraps = (("Crowdloan", "refund"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.Crowdloan.refund(crowdloan_id=self.crowdloan_id))

    def summary(self) -> str:
        return f"refund contributors of crowdloan {self.crowdloan_id}"


@register
@dataclass
class DissolveCrowdloan(_CrowdloanId):
    """Dissolve a fully-refunded crowdloan (creator only)."""

    op = "dissolve_crowdloan"
    signer = "coldkey"
    wraps = (("Crowdloan", "dissolve"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.Crowdloan.dissolve(crowdloan_id=self.crowdloan_id))

    def summary(self) -> str:
        return f"dissolve crowdloan {self.crowdloan_id}"


@register
@dataclass
class WithdrawCrowdloan(_CrowdloanId):
    """Withdraw the creator's contribution from a dissolved/failed crowdloan."""

    op = "withdraw_crowdloan"
    signer = "coldkey"
    wraps = (("Crowdloan", "withdraw"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.Crowdloan.withdraw(crowdloan_id=self.crowdloan_id))

    def summary(self) -> str:
        return f"withdraw from crowdloan {self.crowdloan_id}"


@register
@dataclass
class UpdateCrowdloanCap(Intent):
    """Update the cap of a non-finalized crowdloan (creator only)."""

    op = "update_crowdloan_cap"
    signer = "coldkey"
    wraps = (("Crowdloan", "update_cap"),)

    crowdloan_id: int
    new_cap_tao: float

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Crowdloan.update_cap(
                crowdloan_id=self.crowdloan_id, new_cap=_rao(self.new_cap_tao)
            )
        )

    def summary(self) -> str:
        return f"update crowdloan {self.crowdloan_id} cap to {self.new_cap_tao} TAO"


@register
@dataclass
class UpdateCrowdloanEnd(Intent):
    """Update the end block of a non-finalized crowdloan (creator only)."""

    op = "update_crowdloan_end"
    signer = "coldkey"
    wraps = (("Crowdloan", "update_end"),)

    crowdloan_id: int
    new_end: int

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Crowdloan.update_end(crowdloan_id=self.crowdloan_id, new_end=self.new_end)
        )

    def summary(self) -> str:
        return f"update crowdloan {self.crowdloan_id} end to block {self.new_end}"


@register
@dataclass
class UpdateCrowdloanMinContribution(Intent):
    """Update the minimum contribution of a non-finalized crowdloan (creator only)."""

    op = "update_crowdloan_min_contribution"
    signer = "coldkey"
    wraps = (("Crowdloan", "update_min_contribution"),)

    crowdloan_id: int
    new_min_contribution_tao: float

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Crowdloan.update_min_contribution(
                crowdloan_id=self.crowdloan_id,
                new_min_contribution=_rao(self.new_min_contribution_tao),
            )
        )

    def summary(self) -> str:
        return f"update crowdloan {self.crowdloan_id} min contribution to {self.new_min_contribution_tao} TAO"


@register
@dataclass
class SetCrowdloanMaxContribution(Intent):
    """Set or clear the per-contributor max for a non-finalized crowdloan (creator only)."""

    op = "set_crowdloan_max_contribution"
    signer = "coldkey"
    wraps = (("Crowdloan", "set_max_contribution"),)

    crowdloan_id: int
    new_max_contribution_tao: Optional[float] = None  # None clears the limit

    async def build(self, substrate, wallet: Any):
        new_max = (
            None if self.new_max_contribution_tao is None else _rao(self.new_max_contribution_tao)
        )
        return await substrate.compose(
            calls.Crowdloan.set_max_contribution(
                crowdloan_id=self.crowdloan_id, new_max_contribution=new_max
            )
        )

    def summary(self) -> str:
        if self.new_max_contribution_tao is None:
            return f"clear crowdloan {self.crowdloan_id} max contribution"
        return f"set crowdloan {self.crowdloan_id} max contribution to {self.new_max_contribution_tao} TAO"
