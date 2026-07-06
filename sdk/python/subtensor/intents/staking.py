"""Staking intents: add, remove, and move stake."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from ..balance import Balance
from ._money import alpha_amount, tao_amount
from .base import Intent
from .registry import register


@register
@dataclass
class AddStake(Intent):
    """Stake TAO from the coldkey onto a hotkey."""

    op = "add_stake"
    signer = "coldkey"
    wraps = (("SubtensorModule", "add_stake"),)

    hotkey_ss58: str
    netuid: int
    amount_tao: float  # number (TAO) or a netuid-0 Balance

    def __post_init__(self):
        self.amount_tao = tao_amount(self.amount_tao)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.add_stake(
                hotkey=self.hotkey_ss58,
                netuid=self.netuid,
                amount_staked=Balance.from_tao(self.amount_tao).rao,
            )
        )

    def summary(self) -> str:
        return f"stake {self.amount_tao} TAO to {self.hotkey_ss58} on netuid {self.netuid}"

    def spend_tao(self) -> float:
        return self.amount_tao


@register
@dataclass
class RemoveStake(Intent):
    """Unstake alpha from a hotkey back to the coldkey."""

    op = "remove_stake"
    signer = "coldkey"
    wraps = (("SubtensorModule", "remove_stake"),)

    hotkey_ss58: str
    netuid: int
    amount_alpha: float  # number (alpha) or a Balance tagged with this netuid

    def __post_init__(self):
        self.amount_alpha = alpha_amount(self.amount_alpha, self.netuid)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.remove_stake(
                hotkey=self.hotkey_ss58,
                netuid=self.netuid,
                amount_unstaked=Balance.from_tao(self.amount_alpha, self.netuid).rao,
            )
        )

    def summary(self) -> str:
        return f"unstake {self.amount_alpha} alpha from {self.hotkey_ss58} on netuid {self.netuid}"


@register
@dataclass
class MoveStake(Intent):
    """Move alpha between hotkeys and/or subnets."""

    op = "move_stake"
    signer = "coldkey"
    wraps = (("SubtensorModule", "move_stake"),)

    origin_hotkey_ss58: str
    origin_netuid: int
    dest_hotkey_ss58: str
    dest_netuid: int
    amount_alpha: float  # number (alpha) or a Balance tagged with origin_netuid

    def __post_init__(self):
        self.amount_alpha = alpha_amount(self.amount_alpha, self.origin_netuid)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.move_stake(
                origin_hotkey=self.origin_hotkey_ss58,
                destination_hotkey=self.dest_hotkey_ss58,
                origin_netuid=self.origin_netuid,
                destination_netuid=self.dest_netuid,
                alpha_amount=Balance.from_tao(self.amount_alpha, self.origin_netuid).rao,
            )
        )

    def summary(self) -> str:
        return (
            f"move {self.amount_alpha} alpha from {self.origin_hotkey_ss58} "
            f"(netuid {self.origin_netuid}) to {self.dest_hotkey_ss58} "
            f"(netuid {self.dest_netuid})"
        )

    def touches_netuids(self) -> list[int]:
        return [self.origin_netuid, self.dest_netuid]


@register
@dataclass
class AddStakeLimit(Intent):
    """Stake TAO with a limit price (slippage protection)."""

    op = "add_stake_limit"
    signer = "coldkey"
    wraps = (("SubtensorModule", "add_stake_limit"),)

    hotkey_ss58: str
    netuid: int
    amount_tao: float  # number (TAO) or a netuid-0 Balance
    limit_price_rao: int
    allow_partial: bool = False

    def __post_init__(self):
        self.amount_tao = tao_amount(self.amount_tao)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.add_stake_limit(
                hotkey=self.hotkey_ss58,
                netuid=self.netuid,
                amount_staked=Balance.from_tao(self.amount_tao).rao,
                limit_price=self.limit_price_rao,
                allow_partial=self.allow_partial,
            )
        )

    def summary(self) -> str:
        return (
            f"stake {self.amount_tao} TAO to {self.hotkey_ss58} on netuid {self.netuid} "
            f"(limit {self.limit_price_rao} rao/alpha)"
        )

    def spend_tao(self) -> float:
        return self.amount_tao


@register
@dataclass
class RemoveStakeLimit(Intent):
    """Unstake alpha with a limit price (slippage protection)."""

    op = "remove_stake_limit"
    signer = "coldkey"
    wraps = (("SubtensorModule", "remove_stake_limit"),)

    hotkey_ss58: str
    netuid: int
    amount_alpha: float  # number (alpha) or a Balance tagged with this netuid
    limit_price_rao: int
    allow_partial: bool = False

    def __post_init__(self):
        self.amount_alpha = alpha_amount(self.amount_alpha, self.netuid)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.remove_stake_limit(
                hotkey=self.hotkey_ss58,
                netuid=self.netuid,
                amount_unstaked=Balance.from_tao(self.amount_alpha, self.netuid).rao,
                limit_price=self.limit_price_rao,
                allow_partial=self.allow_partial,
            )
        )

    def summary(self) -> str:
        return (
            f"unstake {self.amount_alpha} alpha from {self.hotkey_ss58} on netuid "
            f"{self.netuid} (limit {self.limit_price_rao} rao/alpha)"
        )


@register
@dataclass
class UnstakeAll(Intent):
    """Unstake everything from a hotkey (root TAO stake)."""

    op = "unstake_all"
    signer = "coldkey"
    wraps = (("SubtensorModule", "unstake_all"),)

    hotkey_ss58: str

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.SubtensorModule.unstake_all(hotkey=self.hotkey_ss58))

    def summary(self) -> str:
        return f"unstake ALL from {self.hotkey_ss58}"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["removes the entire stake from this hotkey"]

    def affects_all_subnets(self) -> bool:
        return True


@register
@dataclass
class UnstakeAllAlpha(Intent):
    """Unstake all alpha from a hotkey across subnets (moves it to root)."""

    op = "unstake_all_alpha"
    signer = "coldkey"
    wraps = (("SubtensorModule", "unstake_all_alpha"),)

    hotkey_ss58: str

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.unstake_all_alpha(hotkey=self.hotkey_ss58)
        )

    def summary(self) -> str:
        return f"unstake ALL alpha from {self.hotkey_ss58}"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["removes all alpha stake from this hotkey across every subnet"]

    def affects_all_subnets(self) -> bool:
        return True


@register
@dataclass
class SwapStake(Intent):
    """Swap stake on one hotkey between two subnets."""

    op = "swap_stake"
    signer = "coldkey"
    wraps = (("SubtensorModule", "swap_stake"),)

    hotkey_ss58: str
    origin_netuid: int
    dest_netuid: int
    amount_alpha: float  # number (alpha) or a Balance tagged with origin_netuid

    def __post_init__(self):
        self.amount_alpha = alpha_amount(self.amount_alpha, self.origin_netuid)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.swap_stake(
                hotkey=self.hotkey_ss58,
                origin_netuid=self.origin_netuid,
                destination_netuid=self.dest_netuid,
                alpha_amount=Balance.from_tao(self.amount_alpha, self.origin_netuid).rao,
            )
        )

    def summary(self) -> str:
        return (
            f"swap {self.amount_alpha} alpha on {self.hotkey_ss58} from netuid "
            f"{self.origin_netuid} to netuid {self.dest_netuid}"
        )

    def touches_netuids(self) -> list[int]:
        return [self.origin_netuid, self.dest_netuid]


@register
@dataclass
class TransferStake(Intent):
    """Transfer stake ownership to another coldkey."""

    op = "transfer_stake"
    signer = "coldkey"
    wraps = (("SubtensorModule", "transfer_stake"),)

    dest_coldkey_ss58: str
    hotkey_ss58: str
    origin_netuid: int
    dest_netuid: int
    amount_alpha: float  # number (alpha) or a Balance tagged with origin_netuid

    def __post_init__(self):
        self.amount_alpha = alpha_amount(self.amount_alpha, self.origin_netuid)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.transfer_stake(
                destination_coldkey=self.dest_coldkey_ss58,
                hotkey=self.hotkey_ss58,
                origin_netuid=self.origin_netuid,
                destination_netuid=self.dest_netuid,
                alpha_amount=Balance.from_tao(self.amount_alpha, self.origin_netuid).rao,
            )
        )

    def summary(self) -> str:
        return (
            f"transfer {self.amount_alpha} alpha (netuid {self.origin_netuid}) to "
            f"coldkey {self.dest_coldkey_ss58}"
        )

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["transfers stake OWNERSHIP to another coldkey"]

    def touches_netuids(self) -> list[int]:
        return [self.origin_netuid, self.dest_netuid]

    def spend_tao(self) -> float:
        # Moves an alpha position out to another coldkey; not TAO-denominated and
        # not cheaply bounded here, so a spend cap must block it until raised.
        return float("inf")


@register
@dataclass
class SetAutoStake(Intent):
    """Auto-stake future mining rewards on a subnet to a chosen hotkey.

    Sets the coldkey's autostake destination for ``netuid``: all future rewards
    on that subnet are automatically staked to ``hotkey_ss58`` (defaults to the
    wallet's hotkey). Read it back with the ``auto_stake`` read.
    """

    op = "set_auto_stake"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_coldkey_auto_stake_hotkey"),)

    netuid: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.set_coldkey_auto_stake_hotkey(netuid=self.netuid, hotkey=hotkey)
        )

    def summary(self) -> str:
        target = self.hotkey_ss58 or "the wallet hotkey"
        return f"auto-stake rewards on netuid {self.netuid} to {target}"
