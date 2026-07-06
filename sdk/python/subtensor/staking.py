"""Staking reads. (Staking mutations are intents; run them via client.execute.)"""

from __future__ import annotations

from typing import Optional

from ._generated.runtime_apis import StakeInfoRuntimeApi
from ._substrate import Substrate
from .balance import Balance


class Staking:
    def __init__(self, substrate: Substrate):
        self._s = substrate

    async def get(
        self,
        coldkey_ss58: str,
        hotkey_ss58: str,
        netuid: int,
        block: Optional[int] = None,
    ) -> Balance:
        """Alpha staked by a coldkey to a hotkey on a subnet (TAO when netuid is 0)."""
        block_hash = await self._s.block_hash(block)
        info = await self._s.runtime_call(
            *StakeInfoRuntimeApi.get_stake_info_for_hotkey_coldkey_netuid,
            [hotkey_ss58, coldkey_ss58, netuid],
            block_hash=block_hash,
        )
        stake_rao = 0 if info is None else int(info["stake"])
        return Balance.from_rao(stake_rao, netuid)
