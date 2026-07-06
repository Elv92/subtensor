"""Coldkey swap: migrate everything a coldkey owns to a new coldkey.

The safe, non-deprecated flow is two steps:

  1. ``announce_coldkey_swap`` publishes only the BlakeTwo256 hash of the new
     coldkey — committing to it without revealing it — and records the block at
     which the swap becomes executable (now + the chain's announcement delay).
  2. after that delay, ``swap_coldkey_announced`` reveals the new coldkey and
     performs the swap.

An announcement can be cleared before execution, and a coldkey holder can
dispute a swap they did not initiate (freezing it for governance to resolve) —
the recovery path if a coldkey is compromised. The older one-shot
``schedule_swap_coldkey`` and the root-only ``swap_coldkey`` / ``reset_coldkey_swap``
stay raw-only on purpose.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from typing import Any

from scalecodec.utils.ss58 import ss58_decode

from .._generated import calls
from .base import Intent
from .registry import register


def coldkey_hash(ss58: str) -> str:
    """BlakeTwo256 (0x-hex) of an account's public key, as ``announce_coldkey_swap`` expects."""
    public_key = bytes.fromhex(ss58_decode(ss58))
    return "0x" + blake2b(public_key, digest_size=32).hexdigest()


@register
@dataclass
class AnnounceColdkeySwap(Intent):
    """Announce (commit to) a coldkey swap; executable after the chain's delay.

    Publishes only the hash of ``new_coldkey_ss58``. Follow up with the
    ``swap_coldkey_announced`` intent once the announcement delay has passed
    (check timing with the ``coldkey_swap_announcement`` read).
    """

    op = "announce_coldkey_swap"
    signer = "coldkey"
    wraps = (("SubtensorModule", "announce_coldkey_swap"),)

    new_coldkey_ss58: str

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.announce_coldkey_swap(
                new_coldkey_hash=coldkey_hash(self.new_coldkey_ss58)
            )
        )

    def summary(self) -> str:
        return f"announce coldkey swap to {self.new_coldkey_ss58}"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return [
            "after the announcement delay, swap_coldkey_announced will move EVERYTHING "
            "this coldkey owns (balance, stake, subnets) to the new coldkey",
            "make sure you control the new coldkey and have its mnemonic backed up",
        ]


@register
@dataclass
class SwapColdkeyAnnounced(Intent):
    """Execute a previously announced coldkey swap (after the delay has passed)."""

    op = "swap_coldkey_announced"
    signer = "coldkey"
    wraps = (("SubtensorModule", "swap_coldkey_announced"),)

    new_coldkey_ss58: str

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.swap_coldkey_announced(new_coldkey=self.new_coldkey_ss58)
        )

    def summary(self) -> str:
        return f"SWAP coldkey to {self.new_coldkey_ss58} (moves all ownership)"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return [
            "irreversible: balance, stake, and subnet ownership move to the new coldkey",
            "the new coldkey must match the announced hash exactly",
        ]

    def affects_all_subnets(self) -> bool:
        return True


@register
@dataclass
class ClearColdkeySwapAnnouncement(Intent):
    """Cancel a pending coldkey swap announcement (after the reannouncement delay)."""

    op = "clear_coldkey_swap_announcement"
    signer = "coldkey"
    wraps = (("SubtensorModule", "clear_coldkey_swap_announcement"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.SubtensorModule.clear_coldkey_swap_announcement())

    def summary(self) -> str:
        return "clear the pending coldkey swap announcement"


@register
@dataclass
class DisputeColdkeySwap(Intent):
    """Freeze this coldkey's pending swap until governance resolves it.

    Use if a swap was announced on your coldkey that you did not initiate
    (i.e. the key may be compromised).
    """

    op = "dispute_coldkey_swap"
    signer = "coldkey"
    wraps = (("SubtensorModule", "dispute_coldkey_swap"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.SubtensorModule.dispute_coldkey_swap())

    def summary(self) -> str:
        return "dispute the pending coldkey swap (freezes it for governance)"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["blocks the swap until the triumvirate resolves the dispute"]
