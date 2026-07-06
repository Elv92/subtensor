"""Transfer intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._generated import calls
from ..balance import Balance
from ._money import tao_amount
from .base import Intent
from .registry import register


@register
@dataclass
class Transfer(Intent):
    """Transfer TAO from the coldkey to a destination address."""

    op = "transfer"
    signer = "coldkey"
    wraps = (
        ("Balances", "transfer_keep_alive"),
        ("Balances", "transfer_allow_death"),
    )

    dest_ss58: str
    amount_tao: float  # number (TAO) or a netuid-0 Balance
    keep_alive: bool = True

    def __post_init__(self):
        self.amount_tao = tao_amount(self.amount_tao)

    async def build(self, substrate, wallet: Any):
        value = Balance.from_tao(self.amount_tao).rao
        call = (
            calls.Balances.transfer_keep_alive(dest=self.dest_ss58, value=value)
            if self.keep_alive
            else calls.Balances.transfer_allow_death(dest=self.dest_ss58, value=value)
        )
        return await substrate.compose(call)

    def summary(self) -> str:
        return f"transfer {self.amount_tao} TAO to {self.dest_ss58}"

    def spend_tao(self) -> float:
        return self.amount_tao


@register
@dataclass
class TransferAll(Intent):
    """Transfer the entire transferable balance to a destination address."""

    op = "transfer_all"
    signer = "coldkey"
    wraps = (("Balances", "transfer_all"),)

    dest_ss58: str
    keep_alive: bool = True

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Balances.transfer_all(dest=self.dest_ss58, keep_alive=self.keep_alive)
        )

    def summary(self) -> str:
        return f"transfer ALL TAO to {self.dest_ss58}"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["transfers the entire transferable balance"]

    def spend_tao(self) -> float:
        # Unbounded: a max_spend policy should block draining the whole account.
        return float("inf")
