"""Weight-setting intents: direct set and timelock commit-reveal.

``normalize`` (max-upscale + u16 quantize, dropping zeros) lives here as the one
canonical implementation; the domain ``weights`` module re-exports it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Sequence

from bittensor_drand import get_encrypted_commit

from .._generated import calls
from .._generated.storage import SubtensorModule as st
from ..result import BittensorError
from ..settings import BLOCKTIME, GLOBAL_MAX_SUBNET_COUNT, U16_MAX
from .base import BuiltCall, Intent
from .registry import register


def normalize(uids: Sequence[int], weights: Sequence[float]) -> tuple[list[int], list[int]]:
    """Max-upscale and quantize weights to u16, dropping zeros.

    Returns parallel ``(uids, values)`` ready for the chain. All-zero input
    returns two empty lists.
    """
    if len(uids) != len(weights):
        raise BittensorError(
            f"uids and weights must be equal length: {len(uids)} vs {len(weights)}."
        )
    if any(w < 0 for w in weights):
        raise BittensorError("Weights must be non-negative.")
    if any(u < 0 for u in uids):
        raise BittensorError("UIDs must be non-negative.")

    top = max(weights) if weights else 0
    if top == 0:
        return [], []

    out_uids: list[int] = []
    out_vals: list[int] = []
    for uid, weight in zip(uids, weights):
        value = round((weight / top) * U16_MAX)
        if value != 0:
            out_uids.append(int(uid))
            out_vals.append(int(value))
    return out_uids, out_vals


@register
@dataclass
class SetWeights(Intent):
    """Set validator weights directly (plaintext)."""

    op = "set_weights"
    signer = "hotkey"
    wraps = (("SubtensorModule", "set_mechanism_weights"),)

    netuid: int
    uids: list[int]
    weights: list[float]
    mechid: int = 0
    version_key: int = 0

    async def build(self, substrate, wallet: Any):
        norm_uids, norm_vals = normalize(self.uids, self.weights)
        if not norm_uids:
            raise BittensorError("All weights are zero; nothing to set.")
        return await substrate.compose(
            calls.SubtensorModule.set_mechanism_weights(
                netuid=self.netuid,
                mecid=self.mechid,
                dests=norm_uids,
                weights=norm_vals,
                version_key=self.version_key,
            )
        )

    def summary(self) -> str:
        return f"set weights on netuid {self.netuid} for {len(self.uids)} uids"


@register
@dataclass
class CommitWeights(Intent):
    """Timelock-encrypt and commit weights (commit-reveal subnets)."""

    op = "commit_weights"
    signer = "hotkey"
    wraps = (("SubtensorModule", "commit_timelocked_mechanism_weights"),)

    netuid: int
    uids: list[int]
    weights: list[float]
    mechid: int = 0
    version_key: int = 0
    commit_reveal_version: int = 4

    async def build(self, substrate, wallet: Any):
        norm_uids, norm_vals = normalize(self.uids, self.weights)
        if not norm_uids:
            raise BittensorError("All weights are zero; nothing to commit.")

        current_block = await substrate.block_number()
        block_hash = await substrate.block_hash(current_block)
        tempo_raw, reveal_raw = await asyncio.gather(
            substrate.query(*st.Tempo, [self.netuid], block_hash=block_hash),
            substrate.query(*st.RevealPeriodEpochs, [self.netuid], block_hash=block_hash),
        )
        storage_index = self.mechid * GLOBAL_MAX_SUBNET_COUNT + self.netuid
        commit_bytes, reveal_round = get_encrypted_commit(
            uids=norm_uids,
            weights=norm_vals,
            version_key=self.version_key,
            tempo=int(tempo_raw),
            current_block=current_block,
            netuid=storage_index,
            subnet_reveal_period_epochs=int(reveal_raw),
            block_time=BLOCKTIME,
            hotkey=wallet.hotkey.public_key,
        )
        call = await substrate.compose(
            calls.SubtensorModule.commit_timelocked_mechanism_weights(
                netuid=self.netuid,
                mecid=self.mechid,
                commit=commit_bytes,
                reveal_round=reveal_round,
                commit_reveal_version=self.commit_reveal_version,
            )
        )
        # Surface the reveal round into the execution result via the sanctioned
        # extras channel (no private attribute on the intent).
        return BuiltCall(call, {"reveal_round": reveal_round})

    def summary(self) -> str:
        return f"commit weights on netuid {self.netuid} for {len(self.uids)} uids"


@register
@dataclass
class RevealWeights(Intent):
    """Reveal previously committed weights (commit-reveal subnets)."""

    op = "reveal_weights"
    signer = "hotkey"
    wraps = (("SubtensorModule", "reveal_weights"),)

    netuid: int
    uids: list[int]
    weights: list[float]
    salt: list[int]
    version_key: int = 0

    async def build(self, substrate, wallet: Any):
        norm_uids, norm_vals = normalize(self.uids, self.weights)
        if not norm_uids:
            raise BittensorError("All weights are zero; nothing to reveal.")
        return await substrate.compose(
            calls.SubtensorModule.reveal_weights(
                netuid=self.netuid,
                uids=norm_uids,
                values=norm_vals,
                salt=[int(x) for x in self.salt],
                version_key=self.version_key,
            )
        )

    def summary(self) -> str:
        return f"reveal weights on netuid {self.netuid} for {len(self.uids)} uids"
