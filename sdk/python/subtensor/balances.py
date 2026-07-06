"""Balance queries (free TAO held by a coldkey)."""

from __future__ import annotations

from typing import Optional

from ._generated import constants, storage
from ._substrate import Substrate
from .balance import Balance


class Balances:
    def __init__(self, substrate: Substrate):
        self._s = substrate

    async def get(self, address: str, block: Optional[int] = None) -> Balance:
        """Free TAO balance of a coldkey address."""
        block_hash = await self._s.block_hash(block)
        account = await self._s.query(*storage.System.Account, [address], block_hash=block_hash)
        return Balance.from_rao(int(account["data"]["free"]))

    async def get_many(
        self, addresses: list[str], block: Optional[int] = None
    ) -> dict[str, Balance]:
        """Free TAO balance for several coldkey addresses in one batched request."""
        block_hash = await self._s.block_hash(block)
        accounts = await self._s.query_batch(
            *storage.System.Account,
            [[address] for address in addresses],
            block_hash=block_hash,
        )
        return {
            address: Balance.from_rao(int(account["data"]["free"]) if account else 0)
            for address, account in zip(addresses, accounts)
        }

    async def existential_deposit(self) -> Balance:
        """Minimum balance an account must keep to stay alive."""
        value = await self._s.constant(*constants.Balances.ExistentialDeposit)
        return Balance.from_rao(int(value))
