"""Swap-pallet liquidity position intents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from ..balance import Balance
from .base import Intent
from .registry import register


@register
@dataclass
class AddLiquidity(Intent):
    """Add liquidity to a tick range on a subnet."""

    op = "add_liquidity"
    signer = "coldkey"
    wraps = (("Swap", "add_liquidity"),)

    netuid: int
    tick_low: int
    tick_high: int
    liquidity: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.Swap.add_liquidity(
                hotkey=hotkey,
                netuid=self.netuid,
                tick_low=self.tick_low,
                tick_high=self.tick_high,
                liquidity=self.liquidity,
            )
        )

    def summary(self) -> str:
        return f"add liquidity on netuid {self.netuid} ticks [{self.tick_low}, {self.tick_high}]"


@register
@dataclass
class ModifyLiquidity(Intent):
    """Modify liquidity in an existing position (positive or negative delta)."""

    op = "modify_liquidity"
    signer = "coldkey"
    wraps = (("Swap", "modify_position"),)

    netuid: int
    position_id: int
    liquidity_delta: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.Swap.modify_position(
                hotkey=hotkey,
                netuid=self.netuid,
                position_id=self.position_id,
                liquidity_delta=self.liquidity_delta,
            )
        )

    def summary(self) -> str:
        return f"modify position {self.position_id} on netuid {self.netuid} by {self.liquidity_delta}"


@register
@dataclass
class RemoveLiquidity(Intent):
    """Remove an entire liquidity position."""

    op = "remove_liquidity"
    signer = "coldkey"
    wraps = (("Swap", "remove_liquidity"),)

    netuid: int
    position_id: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.Swap.remove_liquidity(
                hotkey=hotkey, netuid=self.netuid, position_id=self.position_id
            )
        )

    def summary(self) -> str:
        return f"remove liquidity position {self.position_id} on netuid {self.netuid}"
