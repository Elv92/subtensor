"""Registration and subnet-lifecycle intents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .._generated import calls
from ._money import UNBOUNDED, Spend
from .base import Intent
from .registry import register

# Variants of the runtime's RootClaimTypeEnum (subtensor/pallets/subtensor/src/lib.rs).
ROOT_CLAIM_TYPES = ("Swap", "Keep", "KeepSubnets")

ROOT_CLAIM_TYPE_HELP = (
    "How root alpha emission is claimed. One of: "
    + ", ".join(ROOT_CLAIM_TYPES)
    + ". Swap converts all alpha emission to TAO, Keep keeps everything as alpha, "
    "KeepSubnets keeps alpha only on the subnets given via --subnets and swaps the rest."
)


@register
@dataclass
class BurnedRegister(Intent):
    """Register a hotkey on a subnet by recycling TAO.

    Burns the subnet's current registration cost from the signing coldkey and
    assigns the hotkey a UID on that subnet. The burned TAO is recycled, not
    staked — it cannot be recovered by deregistering. The cost floats with
    registration demand and is only known at execution time, so a configured
    spend cap blocks this call until raised. On a full subnet, registering
    evicts the lowest-ranked non-immune neuron, and the new UID can itself be
    evicted once its immunity period ends. Use ``root_register`` instead for
    the root network (netuid 0).
    """

    op = "burned_register"
    signer = "coldkey"
    wraps = (("SubtensorModule", "burned_register"),)

    netuid: int = field(metadata={"help": "Subnet to register on."})
    hotkey_ss58: Optional[str] = field(
        default=None,
        metadata={"help": "Hotkey that receives the UID; defaults to the wallet's hotkey."},
    )

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.burned_register(netuid=self.netuid, hotkey=hotkey)
        )

    def summary(self) -> str:
        target = self.hotkey_ss58 or "wallet hotkey"
        return f"register {target} on netuid {self.netuid} (burned)"

    def spend(self) -> Spend:
        # Burns the subnet's current registration cost from the coldkey. The exact
        # amount isn't known without a read, so a spend cap must block until raised.
        return UNBOUNDED


@register
@dataclass
class RegisterSubnet(Intent):
    """Create a new subnet owned by the signing coldkey.

    Registers a brand-new subnet with the signing coldkey as its owner and the
    wallet's hotkey as the subnet-owner hotkey. The network registration cost —
    potentially thousands of TAO — is taken from the coldkey; it rises after
    each new subnet registration and decays over time, and is only known at
    execution time, so a configured spend cap blocks this call until raised.
    The new subnet starts inactive: call ``start_call`` once the chain's
    activation delay has passed to enable emissions. This is a major, expensive
    commitment — check the current lock cost before sending.
    """

    op = "register_subnet"
    signer = "coldkey"
    wraps = (("SubtensorModule", "register_network"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.register_network(hotkey=wallet.hotkey.ss58_address)
        )

    def summary(self) -> str:
        return "register a new subnet"

    def spend(self) -> Spend:
        # Locks/burns the network registration cost (can be thousands of TAO).
        return UNBOUNDED


@register
@dataclass
class StartCall(Intent):
    """Activate a subnet (enable emissions / subtoken) as its owner.

    Flips a freshly registered subnet from inactive to active: emissions start
    flowing and the subnet token becomes usable. Owner-only, callable once per
    subnet, and only after the chain's minimum delay since the subnet was
    registered — calling too early fails. Until this is called the subnet earns
    nothing, so run it as soon as the delay allows.
    """

    op = "start_call"
    signer = "coldkey"
    wraps = (("SubtensorModule", "start_call"),)

    netuid: int = field(metadata={"help": "Subnet to activate; the signer must be its owner."})

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.SubtensorModule.start_call(netuid=self.netuid))

    def summary(self) -> str:
        return f"activate subnet {self.netuid}"


@register
@dataclass
class RootRegister(Intent):
    """Register a hotkey on the root network (netuid 0).

    Joins the hotkey to the root network, where members participate in
    cross-subnet governance (the top root members by stake form the senate).
    Placement is stake-based rather than burn-based: root slots are limited, so
    joining a full root network evicts the member with the least stake, and a
    hotkey without enough stake behind it will not hold a seat. Use
    ``burned_register`` for ordinary subnets.
    """

    op = "root_register"
    signer = "coldkey"
    wraps = (("SubtensorModule", "root_register"),)

    hotkey_ss58: Optional[str] = field(
        default=None,
        metadata={
            "help": "Hotkey to register on the root network; defaults to the wallet's hotkey."
        },
    )

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
    """Claim accumulated root dividends from one or more subnets.

    Pays out the signing coldkey's accrued root-stake dividends from the listed
    subnets. What the payout looks like depends on the coldkey's root claim
    type (see ``set_root_claim_type``): swapped to TAO, kept as subnet alpha,
    or a per-subnet mix. Unclaimed dividends simply keep accruing — there is no
    deadline — but each call pays out only the subnets listed.
    """

    op = "claim_root"
    signer = "coldkey"
    wraps = (("SubtensorModule", "claim_root"),)

    subnets: list[int] = field(
        metadata={"help": "Netuids to claim accumulated root dividends from."}
    )

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

    Controls what happens to root dividends when they are claimed (see
    ``claim_root``): ``Swap`` converts all alpha emission to TAO (the chain
    default), ``Keep`` keeps everything as subnet alpha, and ``KeepSubnets``
    keeps alpha on the listed ``subnets`` while swapping the rest. The setting
    is per-coldkey and persists until changed again; it does not move anything
    already claimed. Read it back with the ``root_claim_type`` read.
    """

    op = "set_root_claim_type"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_root_claim_type"),)

    claim_type: str = field(default="Swap", metadata={"help": ROOT_CLAIM_TYPE_HELP})
    subnets: Optional[list] = field(
        default=None,
        metadata={
            "help": "Netuids to keep alpha on; required for KeepSubnets, invalid otherwise."
        },
    )

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
    """Swap a hotkey for a new one (all subnets, or one netuid).

    Re-keys the neuron identity: the old hotkey's registrations, stake, and
    history move to ``new_hotkey_ss58``, either everywhere (``netuid`` omitted)
    or on a single subnet. The old hotkey stops earning immediately, so update
    running miners/validators to sign with the new key at the same time. The
    new hotkey must not already be registered where the swap applies, and
    hotkey swaps are rate-limited by the chain, so plan the change rather than
    iterating. This rotates a leaked hotkey without touching the coldkey; a
    compromised coldkey needs a coldkey swap instead.
    """

    op = "swap_hotkey"
    signer = "coldkey"
    wraps = (("SubtensorModule", "swap_hotkey"),)

    new_hotkey_ss58: str = field(
        metadata={
            "help": "Replacement hotkey that takes over the old hotkey's registrations and stake."
        }
    )
    hotkey_ss58: Optional[str] = field(
        default=None,
        metadata={"help": "Hotkey being replaced; defaults to the wallet's hotkey."},
    )
    netuid: Optional[int] = field(
        default=None,
        metadata={"help": "Limit the swap to this subnet; omit to swap across all subnets."},
    )

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
