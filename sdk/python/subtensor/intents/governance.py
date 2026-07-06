"""Subnet-owner and governance intents not covered by hyperparameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from .._generated.calls import Call
from ..balance import Balance
from ._money import tao_amount
from .base import Intent
from .registry import register


@register
@dataclass
class TrimSubnet(Intent):
    """Trim a subnet to at most ``max_n`` UIDs (subnet owner)."""

    op = "trim_subnet"
    signer = "coldkey"
    wraps = (("AdminUtils", "sudo_trim_to_max_allowed_uids"),)

    netuid: int
    max_n: int

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.AdminUtils.sudo_trim_to_max_allowed_uids(netuid=self.netuid, max_n=self.max_n)
        )

    def summary(self) -> str:
        return f"trim netuid {self.netuid} to at most {self.max_n} UIDs"


@register
@dataclass
class StakeBurn(Intent):
    """Buy back / burn stake via the stake-burn extrinsic."""

    op = "stake_burn"
    signer = "coldkey"
    wraps = (("SubtensorModule", "add_stake_burn"),)

    netuid: int
    amount_tao: float
    limit_price: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        amount = int(Balance.from_tao(tao_amount(self.amount_tao)).rao)
        return await substrate.compose(
            calls.SubtensorModule.add_stake_burn(
                hotkey=hotkey, netuid=self.netuid, amount=amount, limit=self.limit_price
            )
        )

    def summary(self) -> str:
        return f"stake burn {self.amount_tao} TAO on netuid {self.netuid}"

    def spend_tao(self) -> float:
        return tao_amount(self.amount_tao)


@register
@dataclass
class SenateVote(Intent):
    """Cast a senate vote on a proposal (hotkey must be a senate member)."""

    op = "senate_vote"
    signer = "hotkey"
    wraps = (("SubtensorModule", "vote"),)

    hotkey_ss58: Optional[str] = None
    proposal_hash: str = ""
    index: int = 0
    approve: bool = True

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            Call(
                "SubtensorModule",
                "vote",
                {
                    "hotkey": hotkey,
                    "proposal": bytes.fromhex(self.proposal_hash.removeprefix("0x")),
                    "index": self.index,
                    "approve": self.approve,
                },
            )
        )

    def summary(self) -> str:
        vote = "approve" if self.approve else "reject"
        return f"senate {vote} proposal index {self.index}"


@register
@dataclass
class SetMechanismCount(Intent):
    """Set the number of mechanisms on a subnet."""

    op = "set_mechanism_count"
    signer = "coldkey"
    wraps = (("AdminUtils", "sudo_set_mechanism_count"),)

    netuid: int
    mechanism_count: int

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.AdminUtils.sudo_set_mechanism_count(
                netuid=self.netuid, mechanism_count=self.mechanism_count
            )
        )

    def summary(self) -> str:
        return f"set mechanism count to {self.mechanism_count} on netuid {self.netuid}"


@register
@dataclass
class SetMechanismEmissionSplit(Intent):
    """Set emission split between mechanisms on a subnet."""

    op = "set_mechanism_emission_split"
    signer = "coldkey"
    wraps = (("AdminUtils", "sudo_set_mechanism_emission_split"),)

    netuid: int
    split: list[int]

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.AdminUtils.sudo_set_mechanism_emission_split(
                netuid=self.netuid, maybe_split=[int(x) for x in self.split]
            )
        )

    def summary(self) -> str:
        return f"set mechanism emission split on netuid {self.netuid}: {self.split}"


@register
@dataclass
class UpdateSymbol(Intent):
    """Update a subnet's symbol (utf-8 bytes on chain)."""

    op = "update_symbol"
    signer = "coldkey"
    wraps = (("SubtensorModule", "update_symbol"),)

    netuid: int
    symbol: str

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.update_symbol(
                netuid=self.netuid, symbol=self.symbol.encode("utf-8")
            )
        )

    def summary(self) -> str:
        return f"set symbol for netuid {self.netuid} to {self.symbol!r}"
