"""Subnet-owner and governance intents not covered by hyperparameters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .._generated import calls
from .._generated.calls import Call
from ._money import Money, Spend, tao_amount
from .base import Intent
from .registry import register


@register
@dataclass
class TrimSubnet(Intent):
    """Trim a subnet to at most ``max_n`` UIDs (subnet owner).

    Lowers the subnet's UID capacity and immediately deregisters the
    lowest-ranked neurons above the new limit — those miners lose their slots
    and would have to re-register (paying the burn cost) to return. Owner-only
    and disruptive to affected participants, so announce it before shrinking a
    live subnet. To simply cap future growth without evicting anyone, set the
    ``max_allowed_uids`` hyperparameter to a value at or above the current UID
    count instead.
    """

    op = "trim_subnet"
    signer = "coldkey"
    wraps = (("AdminUtils", "sudo_trim_to_max_allowed_uids"),)

    netuid: int = field(metadata={"help": "Subnet to trim; the signer must be its owner."})
    max_n: int = field(
        metadata={
            "help": "New maximum number of UIDs; lowest-ranked neurons above this are removed."
        }
    )

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.AdminUtils.sudo_trim_to_max_allowed_uids(netuid=self.netuid, max_n=self.max_n)
        )

    def summary(self) -> str:
        return f"trim netuid {self.netuid} to at most {self.max_n} UIDs"


@register
@dataclass
class StakeBurn(Intent):
    """Buy back / burn stake via the stake-burn extrinsic.

    Spends TAO from the signing coldkey to buy the subnet's alpha and burn it,
    reducing alpha supply (a buyback-and-burn) rather than adding to the
    signer's stake. The TAO is spent permanently — nothing lands in your stake,
    so this is not an investment call; use a regular add-stake intent to
    acquire a position. ``limit_price`` bounds the execution price so the swap
    fails instead of filling at a worse rate. Counts against a configured
    spend cap.
    """

    op = "stake_burn"
    signer = "coldkey"
    wraps = (("SubtensorModule", "add_stake_burn"),)

    netuid: int = field(metadata={"help": "Subnet whose alpha is bought and burned."})
    amount_tao: Money = field(
        metadata={"help": "Spent from the coldkey to buy alpha that is then burned."}
    )
    limit_price: int = field(
        metadata={
            "help": "Worst acceptable price in rao per alpha; the call fails rather than "
            "filling beyond it."
        }
    )
    hotkey_ss58: Optional[str] = field(
        default=None,
        metadata={"help": "Hotkey the burn is routed through; defaults to the wallet's hotkey."},
    )

    def __post_init__(self):
        self.amount_tao = tao_amount(self.amount_tao)

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(
            calls.SubtensorModule.add_stake_burn(
                hotkey=hotkey,
                netuid=self.netuid,
                amount=self.amount_tao.rao,
                limit=self.limit_price,
            )
        )

    def summary(self) -> str:
        return f"stake burn {self.amount_tao} on netuid {self.netuid}"

    def spend(self) -> Spend:
        return self.amount_tao


@register
@dataclass
class SenateVote(Intent):
    """Cast a senate vote on a proposal (hotkey must be a senate member).

    Records an approve/reject vote on an open governance proposal, signed by
    the hotkey (not the coldkey — senate membership is tied to the hotkey).
    Fails if the hotkey is not currently a senate member or if the proposal
    hash and index do not match an open proposal. Votes matter until the
    proposal closes; find open proposals and their hashes via the chain's
    triumvirate/senate proposal state.
    """

    op = "senate_vote"
    signer = "hotkey"
    wraps = (("SubtensorModule", "vote"),)

    hotkey_ss58: Optional[str] = field(
        default=None,
        metadata={
            "help": "Senate-member hotkey casting the vote; defaults to the wallet's hotkey."
        },
    )
    proposal_hash: str = field(
        default="", metadata={"help": "Hash of the proposal being voted on, as 0x-hex."}
    )
    index: int = field(
        default=0, metadata={"help": "Index of the proposal in the active proposal list."}
    )
    approve: bool = field(
        default=True, metadata={"help": "True to vote in favor, false to vote against."}
    )

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
    """Set the number of mechanisms on a subnet.

    Mechanisms are independent incentive sub-markets within one subnet, each
    running its own weights and consensus; this owner-only call sets how many
    the subnet runs. Increasing the count opens new mechanisms; decreasing it
    removes the highest-numbered ones and the miner state in them. Pair with
    ``set_mechanism_emission_split`` to control how emissions divide across
    mechanisms; the chain caps how many mechanisms a subnet may have.
    """

    op = "set_mechanism_count"
    signer = "coldkey"
    wraps = (("AdminUtils", "sudo_set_mechanism_count"),)

    netuid: int = field(metadata={"help": "Subnet to configure; the signer must be its owner."})
    mechanism_count: int = field(
        metadata={"help": "Number of mechanisms the subnet should run."}
    )

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
    """Set emission split between mechanisms on a subnet.

    Owner-only: divides the subnet's emission between its mechanisms. The list
    gives one weight per mechanism, in order; each mechanism receives emission
    in proportion to its weight relative to the total. The list length must
    match the subnet's current mechanism count (see ``set_mechanism_count``),
    or the call fails. Changing the split reallocates future emission only —
    nothing already emitted moves.
    """

    op = "set_mechanism_emission_split"
    signer = "coldkey"
    wraps = (("AdminUtils", "sudo_set_mechanism_emission_split"),)

    netuid: int = field(metadata={"help": "Subnet to configure; the signer must be its owner."})
    split: list[int] = field(
        metadata={
            "help": "Relative emission weight per mechanism, in mechanism order; one entry "
            "per mechanism."
        }
    )

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
    """Update a subnet's symbol (utf-8 bytes on chain).

    Owner-only cosmetic call: changes the short ticker shown for the subnet's
    alpha token in wallets, explorers, and CLIs. The string is stored on chain
    as raw utf-8 bytes and the chain enforces its own validity rules (length,
    uniqueness), so a symbol already taken by another subnet is rejected. No
    economic effect — balances, stake, and emissions are untouched.
    """

    op = "update_symbol"
    signer = "coldkey"
    wraps = (("SubtensorModule", "update_symbol"),)

    netuid: int = field(
        metadata={"help": "Subnet whose symbol to change; the signer must be its owner."}
    )
    symbol: str = field(
        metadata={"help": "New token symbol for the subnet, stored on chain as utf-8."}
    )

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.update_symbol(
                netuid=self.netuid, symbol=self.symbol.encode("utf-8")
            )
        )

    def summary(self) -> str:
        return f"set symbol for netuid {self.netuid} to {self.symbol!r}"
