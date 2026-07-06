"""Child hotkeys and delegate take."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from .._generated import storage as st
from ..settings import U16_MAX
from .base import Intent
from .registry import register


@register
@dataclass
class SetChildren(Intent):
    """Assign child hotkeys with proportions on a subnet.

    ``children`` is a list of ``[proportion, hotkey_ss58]`` pairs, where
    proportion is a u64 share (of u64::MAX) delegated to that child.
    """

    op = "set_children"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_children"),)

    netuid: int
    children: list
    hotkey_ss58: Optional[str] = None  # defaults to the wallet's hotkey

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        children = [(int(prop), child) for prop, child in self.children]
        return await substrate.compose(
            calls.SubtensorModule.set_children(hotkey=hotkey, netuid=self.netuid, children=children)
        )

    def summary(self) -> str:
        return f"set {len(self.children)} child hotkeys on netuid {self.netuid}"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["delegates a share of this hotkey's stake weight to the children"]


@register
@dataclass
class SetChildkeyTake(Intent):
    """Set the childkey take (u16 proportion) for a hotkey on a subnet."""

    op = "set_childkey_take"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_childkey_take"),)

    netuid: int
    take: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.set_childkey_take(
                hotkey=hotkey, netuid=self.netuid, take=self.take
            )
        )

    def summary(self) -> str:
        return f"set childkey take to {self.take}/{U16_MAX} on netuid {self.netuid}"


@register
@dataclass
class IncreaseTake(Intent):
    """Increase the delegate take (u16 proportion) of a hotkey."""

    op = "increase_take"
    signer = "coldkey"
    wraps = (("SubtensorModule", "increase_take"),)

    take: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.increase_take(hotkey=hotkey, take=self.take)
        )

    def summary(self) -> str:
        return f"increase delegate take to {self.take}/{U16_MAX}"


@register
@dataclass
class DecreaseTake(Intent):
    """Decrease the delegate take (u16 proportion) of a hotkey."""

    op = "decrease_take"
    signer = "coldkey"
    wraps = (("SubtensorModule", "decrease_take"),)

    take: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.decrease_take(hotkey=hotkey, take=self.take)
        )

    def summary(self) -> str:
        return f"decrease delegate take to {self.take}/{U16_MAX}"


@register
@dataclass
class SetTake(Intent):
    """Set the delegate take to an absolute u16 value.

    Sugar over the chain's directional ``increase_take`` / ``decrease_take``: it
    reads the current take and dispatches whichever call moves it to ``take``.
    """

    op = "set_take"
    signer = "coldkey"
    wraps = (
        ("SubtensorModule", "increase_take"),
        ("SubtensorModule", "decrease_take"),
    )

    take: int
    hotkey_ss58: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        item = st.SubtensorModule.Delegates
        current = int(await substrate.query(item[0], item[1], [hotkey]) or 0)
        call = (
            calls.SubtensorModule.decrease_take(hotkey=hotkey, take=self.take)
            if self.take < current
            else calls.SubtensorModule.increase_take(hotkey=hotkey, take=self.take)
        )
        return await substrate.compose(call)

    def summary(self) -> str:
        return f"set delegate take to {self.take}/{U16_MAX}"
