"""Stake-lock and conviction intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from ..balance import Balance
from ._money import alpha_amount
from .base import Intent
from .registry import register


@register
@dataclass
class LockStake(Intent):
    """Lock alpha stake on a subnet hotkey, building conviction over time."""

    op = "lock_stake"
    signer = "coldkey"
    wraps = (("SubtensorModule", "lock_stake"),)

    netuid: int
    amount_alpha: float
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        rao = int(Balance.from_tao(alpha_amount(self.amount_alpha, self.netuid), self.netuid).rao)
        return await substrate.compose(
            calls.SubtensorModule.lock_stake(hotkey=hotkey, netuid=self.netuid, amount=rao)
        )

    def summary(self) -> str:
        return f"lock {self.amount_alpha} alpha on netuid {self.netuid}"


@register
@dataclass
class SetPerpetualLock(Intent):
    """Enable or disable perpetual lock mode for a coldkey on a subnet."""

    op = "set_perpetual_lock"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_perpetual_lock"),)

    netuid: int
    enabled: bool

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.set_perpetual_lock(netuid=self.netuid, enabled=self.enabled)
        )

    def summary(self) -> str:
        mode = "perpetual" if self.enabled else "decaying"
        return f"set lock mode to {mode} on netuid {self.netuid}"


@register
@dataclass
class MoveLock(Intent):
    """Move an existing lock from one hotkey to another on a subnet."""

    op = "move_lock"
    signer = "coldkey"
    wraps = (("SubtensorModule", "move_lock"),)

    netuid: int
    destination_hotkey_ss58: str

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.move_lock(
                destination_hotkey=self.destination_hotkey_ss58, netuid=self.netuid
            )
        )

    def summary(self) -> str:
        return f"move lock on netuid {self.netuid} to {self.destination_hotkey_ss58}"
