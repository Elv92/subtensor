"""Stake-lock and conviction intents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .._generated import calls
from ._money import Money, alpha_amount
from .base import Intent
from .registry import register


@register
@dataclass
class LockStake(Intent):
    """Lock alpha stake on a subnet hotkey, building conviction over time.

    Commits an existing alpha position on the subnet as locked stake: the
    locked amount builds conviction the longer it stays locked, but cannot be
    unstaked or moved while the lock is in effect. You must already hold at
    least that much stake on the hotkey (defaulting to the wallet's own
    hotkey) at the subnet. Whether the lock decays over time or persists is
    controlled per subnet with ``set_perpetual_lock``; the lock can be pointed
    at a different hotkey later with ``move_lock``. Only lock what you can
    afford to leave illiquid.
    """

    op = "lock_stake"
    signer = "coldkey"
    wraps = (("SubtensorModule", "lock_stake"),)

    netuid: int = field(metadata={"help": "Subnet the locked stake lives on."})
    amount_alpha: Money = field(
        metadata={"help": "How much of the existing stake to lock."}
    )
    hotkey_ss58: Optional[str] = field(
        default=None,
        metadata={
            "help": "Hotkey holding the stake to lock. Defaults to the wallet's own hotkey."
        },
    )

    def __post_init__(self):
        self.amount_alpha = alpha_amount(self.amount_alpha, self.netuid)

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.lock_stake(
                hotkey=hotkey, netuid=self.netuid, amount=self.amount_alpha.rao
            )
        )

    def summary(self) -> str:
        return f"lock {self.amount_alpha} on netuid {self.netuid}"


@register
@dataclass
class SetPerpetualLock(Intent):
    """Enable or disable perpetual lock mode for a coldkey on a subnet.

    Switches how the signing coldkey's stake lock on the subnet behaves over
    time: perpetual mode keeps the lock (and its conviction) in force
    indefinitely, while decaying mode lets it wind down over time so the
    stake eventually becomes liquid again. A per-coldkey, per-subnet setting
    that moves no funds by itself — it changes the behavior of locks created
    with ``lock_stake``. Enabling perpetual mode means the locked stake stays
    illiquid until you switch back to decaying and the lock runs off.
    """

    op = "set_perpetual_lock"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_perpetual_lock"),)

    netuid: int = field(metadata={"help": "Subnet whose lock mode is changed."})
    enabled: bool = field(
        metadata={
            "help": "True for perpetual mode (lock never decays), false for decaying mode."
        }
    )

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
    """Move an existing lock from one hotkey to another on a subnet.

    Re-points the signing coldkey's entire stake lock on the subnet at the
    destination hotkey, carrying the locked position with it. Use it to keep
    accrued conviction while switching which hotkey the lock backs — for
    example when rotating validators — since unstaking is not possible while
    the lock is in force. Fails if there is no existing lock on the subnet to
    move.
    """

    op = "move_lock"
    signer = "coldkey"
    wraps = (("SubtensorModule", "move_lock"),)

    netuid: int = field(metadata={"help": "Subnet the lock lives on."})
    destination_hotkey_ss58: str = field(
        metadata={"help": "Hotkey the lock is moved to."}
    )

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.move_lock(
                destination_hotkey=self.destination_hotkey_ss58, netuid=self.netuid
            )
        )

    def summary(self) -> str:
        return f"move lock on netuid {self.netuid} to {self.destination_hotkey_ss58}"
