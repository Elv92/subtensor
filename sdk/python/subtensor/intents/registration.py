"""Registration and subnet-lifecycle intents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .._generated import calls
from .base import Intent
from .registry import register

# Variants of the runtime's RootClaimTypeEnum (subtensor/pallets/subtensor/src/lib.rs).
ROOT_CLAIM_TYPES = ("Swap", "Keep", "KeepSubnets")


@register
@dataclass
class BurnedRegister(Intent):
    """Register a hotkey on a subnet by recycling TAO."""

    op = "burned_register"
    signer = "coldkey"
    wraps = (("SubtensorModule", "burned_register"),)

    netuid: int
    hotkey_ss58: Optional[str] = None  # defaults to the wallet's hotkey

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.burned_register(netuid=self.netuid, hotkey=hotkey)
        )

    def summary(self) -> str:
        target = self.hotkey_ss58 or "wallet hotkey"
        return f"register {target} on netuid {self.netuid} (burned)"

    def spend_tao(self) -> float:
        # Burns the subnet's current registration cost from the coldkey. The exact
        # amount isn't known without a read, so a spend cap must block until raised.
        return float("inf")


@register
@dataclass
class RegisterSubnet(Intent):
    """Create a new subnet owned by the signing coldkey."""

    op = "register_subnet"
    signer = "coldkey"
    wraps = (("SubtensorModule", "register_network"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.register_network(hotkey=wallet.hotkey.ss58_address)
        )

    def summary(self) -> str:
        return "register a new subnet"

    def spend_tao(self) -> float:
        # Locks/burns the network registration cost (can be thousands of TAO).
        return float("inf")


@register
@dataclass
class StartCall(Intent):
    """Activate a subnet (enable emissions / subtoken) as its owner."""

    op = "start_call"
    signer = "coldkey"
    wraps = (("SubtensorModule", "start_call"),)

    netuid: int

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.SubtensorModule.start_call(netuid=self.netuid))

    def summary(self) -> str:
        return f"activate subnet {self.netuid}"


@register
@dataclass
class RootRegister(Intent):
    """Register a hotkey on the root network (netuid 0)."""

    op = "root_register"
    signer = "coldkey"
    wraps = (("SubtensorModule", "root_register"),)

    hotkey_ss58: Optional[str] = None  # defaults to the wallet's hotkey

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(calls.SubtensorModule.root_register(hotkey=hotkey))

    def summary(self) -> str:
        return f"register {self.hotkey_ss58 or 'wallet hotkey'} on the root network"

    def touches_netuids(self) -> list[int]:
        return [0]


@register
@dataclass
class ClaimRoot(Intent):
    """Claim accumulated root dividends from one or more subnets."""

    op = "claim_root"
    signer = "coldkey"
    wraps = (("SubtensorModule", "claim_root"),)

    subnets: list[int]

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.claim_root(subnets=[int(n) for n in self.subnets])
        )

    def summary(self) -> str:
        return f"claim root dividends from subnets {self.subnets}"


@register
@dataclass
class SetRootClaimType(Intent):
    """Set how a coldkey's root alpha emission is claimed.

    ``claim_type`` is one of: ``Swap`` (swap all alpha emission for TAO — the
    default), ``Keep`` (keep all alpha), or ``KeepSubnets`` (keep alpha on the
    given ``subnets``, swap everything else). ``subnets`` is required only for
    ``KeepSubnets``. Read it back with the ``root_claim_type`` read.
    """

    op = "set_root_claim_type"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_root_claim_type"),)

    claim_type: str = "Swap"
    subnets: Optional[list] = field(default=None)

    def __post_init__(self):
        if self.claim_type not in ROOT_CLAIM_TYPES:
            raise ValueError(
                f"claim_type must be one of {ROOT_CLAIM_TYPES}, got {self.claim_type!r}"
            )
        if self.claim_type == "KeepSubnets" and not self.subnets:
            raise ValueError("claim_type 'KeepSubnets' requires a non-empty subnets list")
        if self.claim_type != "KeepSubnets" and self.subnets:
            raise ValueError(
                f"subnets is only valid for claim_type 'KeepSubnets', not {self.claim_type!r}"
            )

    async def build(self, substrate, wallet: Any):
        if self.claim_type == "KeepSubnets":
            value: Any = {"KeepSubnets": {"subnets": sorted({int(n) for n in self.subnets})}}
        else:
            value = self.claim_type
        return await substrate.compose(
            calls.SubtensorModule.set_root_claim_type(new_root_claim_type=value)
        )

    def summary(self) -> str:
        if self.claim_type == "KeepSubnets":
            return f"set root claim type to keep alpha on subnets {sorted(self.subnets)}"
        return f"set root claim type to {self.claim_type}"


@register
@dataclass
class SwapHotkey(Intent):
    """Swap a hotkey for a new one (all subnets, or one netuid)."""

    op = "swap_hotkey"
    signer = "coldkey"
    wraps = (("SubtensorModule", "swap_hotkey"),)

    new_hotkey_ss58: str
    hotkey_ss58: Optional[str] = None  # old hotkey; defaults to the wallet's hotkey
    netuid: Optional[int] = None  # None = swap across all subnets

    async def build(self, substrate, wallet: Any):
        old = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.swap_hotkey(
                hotkey=old, new_hotkey=self.new_hotkey_ss58, netuid=self.netuid
            )
        )

    def summary(self) -> str:
        scope = f"netuid {self.netuid}" if self.netuid is not None else "all subnets"
        return f"swap hotkey to {self.new_hotkey_ss58} ({scope})"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["re-keys the neuron identity; the old hotkey stops earning"]
