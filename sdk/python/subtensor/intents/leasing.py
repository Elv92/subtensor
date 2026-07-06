"""Subnet leasing: register a crowdloan-funded leased subnet, and terminate it.

A leased subnet is created with crowdloan funds; contributors receive a share of
its emissions as dividends, and the beneficiary operates it through a proxy. If
the lease has an end block, the beneficiary can take full ownership after it
passes by terminating the lease. Inspect leases with the ``lease`` / ``leases``
reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from .base import Intent
from .registry import register


@register
@dataclass
class RegisterLeasedNetwork(Intent):
    """Register a new crowdloan-funded leased subnet.

    ``emissions_share`` is the percent (0-100) of emissions paid to contributors
    as dividends. ``end_block`` is when the lease ends and the beneficiary can
    take ownership; omit it for a perpetual lease. Must be called in a crowdloan
    context (the crowdloan's funds pay the lock cost).
    """

    op = "register_leased_network"
    signer = "coldkey"
    wraps = (("SubtensorModule", "register_leased_network"),)

    emissions_share: int
    end_block: Optional[int] = None

    def __post_init__(self):
        if not 0 <= self.emissions_share <= 100:
            raise ValueError(f"emissions_share must be a percent 0-100, got {self.emissions_share}")

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.register_leased_network(
                emissions_share=self.emissions_share, end_block=self.end_block
            )
        )

    def summary(self) -> str:
        horizon = f"until block {self.end_block}" if self.end_block is not None else "perpetual"
        return f"register leased subnet ({self.emissions_share}% to contributors, {horizon})"

    def spend_tao(self) -> float:
        # Lock cost is drawn from crowdloan funds with a leftover charged to the
        # beneficiary; not cheaply boundable, so a spend cap must block it.
        return float("inf")


@register
@dataclass
class TerminateLease(Intent):
    """Terminate an ended lease and take subnet ownership (beneficiary only)."""

    op = "terminate_lease"
    signer = "coldkey"
    wraps = (("SubtensorModule", "terminate_lease"),)

    lease_id: int
    hotkey_ss58: Optional[str] = None  # beneficiary hotkey to mark as owner; defaults to wallet's

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.terminate_lease(lease_id=self.lease_id, hotkey=hotkey)
        )

    def summary(self) -> str:
        return f"terminate lease {self.lease_id} and take subnet ownership"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["only succeeds after the lease's end block has passed"]
