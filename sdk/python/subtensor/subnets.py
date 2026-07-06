"""Subnet queries: which subnets exist, burn cost, tempo."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from ._generated.storage import SubtensorModule as st
from ._substrate import Substrate
from .balance import Balance


@dataclass
class SubnetInfo:
    netuid: int
    tempo: int
    burn: Balance
    neuron_count: int


class Subnets:
    """Aggregating/decoding subnet reads. For a single raw value (e.g. does netuid
    N exist), use the generic ``client.query(storage.SubtensorModule.NetworksAdded,
    [netuid])`` accessor instead of a bespoke method.
    """

    def __init__(self, substrate: Substrate):
        self._s = substrate

    async def burn(self, netuid: int, block: Optional[int] = None) -> Balance:
        """Current burn (recycle) cost to register on a subnet."""
        block_hash = await self._s.block_hash(block)
        value = await self._s.query(*st.Burn, [netuid], block_hash=block_hash)
        return Balance.from_rao(int(value))

    async def commit_reveal_enabled(self, netuid: int, block: Optional[int] = None) -> bool:
        """Whether commit-reveal weights are enabled on a subnet."""
        block_hash = await self._s.block_hash(block)
        value = await self._s.query(*st.CommitRevealWeightsEnabled, [netuid], block_hash=block_hash)
        return bool(value)

    async def info(self, netuid: int, block: Optional[int] = None) -> SubnetInfo:
        """Tempo, burn, and neuron count for one subnet (the three reads run concurrently)."""
        block_hash = await self._s.block_hash(block)
        tempo, burn, count = await asyncio.gather(
            self._s.query(*st.Tempo, [netuid], block_hash=block_hash),
            self._s.query(*st.Burn, [netuid], block_hash=block_hash),
            self._s.query(*st.SubnetworkN, [netuid], block_hash=block_hash),
        )
        return SubnetInfo(
            netuid=netuid,
            tempo=int(tempo),
            burn=Balance.from_rao(int(burn)),
            neuron_count=int(count or 0),
        )

    async def all(self, block: Optional[int] = None) -> list[SubnetInfo]:
        """Info for every subnet, fetched in four batched map queries rather than
        one-query-per-subnet. This is what listing should use.
        """
        block_hash = await self._s.block_hash(block)
        added, tempos, burns, counts = await asyncio.gather(
            self._s.query_map(*st.NetworksAdded, block_hash=block_hash),
            self._s.query_map(*st.Tempo, block_hash=block_hash),
            self._s.query_map(*st.Burn, block_hash=block_hash),
            self._s.query_map(*st.SubnetworkN, block_hash=block_hash),
        )
        tempo_map = {int(k): int(v) for k, v in tempos}
        burn_map = {int(k): int(v) for k, v in burns}
        count_map = {int(k): int(v or 0) for k, v in counts}
        netuids = sorted(int(k) for k, is_added in added if is_added)
        return [
            SubnetInfo(
                netuid=netuid,
                tempo=tempo_map.get(netuid, 0),
                burn=Balance.from_rao(burn_map.get(netuid, 0)),
                neuron_count=count_map.get(netuid, 0),
            )
            for netuid in netuids
        ]
