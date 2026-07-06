"""Shared helpers for CLI commands that aggregate wallet or chain data."""

from __future__ import annotations

import asyncio
from typing import Optional

from .. import wallets
from ..balance import Balance
from ..client import Client
from ..reads import StakePosition


def list_coldkeys(path: str) -> list[tuple[str, str]]:
    """Return ``(wallet_name, coldkey_ss58)`` for every coldkey under ``path``."""
    out: list[tuple[str, str]] = []
    for ck in wallets.list_wallets_detailed(path):
        if ck.ss58:
            out.append((ck.name, ck.ss58))
    return out


def _staked_from_positions(positions: list[StakePosition]) -> Balance:
    return Balance.from_rao(sum(int(p.stake.rao) for p in positions))


def _wallet_balance_row(
    name: str, coldkey_ss58: str, free: Balance, staked: Balance
) -> dict[str, object]:
    total = Balance.from_rao(free.rao + staked.rao)
    return {
        "wallet": name,
        "coldkey": coldkey_ss58,
        "free": free,
        "free_tao": free.tao,
        "staked": staked,
        "staked_tao": staked.tao,
        "total": total,
        "total_tao": total.tao,
    }


async def fetch_coldkey_balances_and_stakes(
    client: Client, coldkeys: list[tuple[str, str]]
) -> tuple[dict[str, Balance], dict[str, list[StakePosition]]]:
    """Free balances and stake positions for many coldkeys in two batched RPC calls."""
    ss58s = [ss58 for _, ss58 in coldkeys]
    free_by_addr, stakes_by_addr = await asyncio.gather(
        client.balances.get_many(ss58s),
        client.read("stake_for_coldkeys", coldkey_ss58s=ss58s),
    )
    return free_by_addr, stakes_by_addr


async def wallet_balance_row(
    client: Client, name: str, coldkey_ss58: str
) -> dict[str, object]:
    """Free, staked, and total balance for one coldkey."""
    free, positions = await asyncio.gather(
        client.balances.get(coldkey_ss58),
        client.read("stake_for_coldkey", coldkey_ss58=coldkey_ss58),
    )
    return _wallet_balance_row(name, coldkey_ss58, free, _staked_from_positions(positions))


async def wallet_balance_rows(
    client: Client, coldkeys: list[tuple[str, str]]
) -> list[dict[str, object]]:
    """Free, staked, and total balance for many coldkeys in two batched RPC calls."""
    if not coldkeys:
        return []
    free_by_addr, stakes_by_addr = await fetch_coldkey_balances_and_stakes(client, coldkeys)
    rows: list[dict[str, object]] = []
    for name, ss58 in coldkeys:
        free = free_by_addr[ss58]
        staked = _staked_from_positions(stakes_by_addr.get(ss58, []))
        rows.append(_wallet_balance_row(name, ss58, free, staked))
    return rows


def _filter_stakes(
    positions: list[StakePosition], netuid: Optional[int]
) -> list[StakePosition]:
    if netuid is None:
        return positions
    return [position for position in positions if position.netuid == netuid]


async def wallet_overview_rows(
    client: Client,
    coldkeys: list[tuple[str, str]],
    netuid: Optional[int] = None,
) -> list[dict[str, object]]:
    """Stake overview for many coldkeys in two batched RPC calls."""
    if not coldkeys:
        return []
    free_by_addr, stakes_by_addr = await fetch_coldkey_balances_and_stakes(client, coldkeys)
    rows: list[dict[str, object]] = []
    for name, ss58 in coldkeys:
        free = free_by_addr[ss58]
        staked = _staked_from_positions(stakes_by_addr.get(ss58, []))
        balance = _wallet_balance_row(name, ss58, free, staked)
        stakes = _filter_stakes(stakes_by_addr.get(ss58, []), netuid)
        rows.append(
            {
                "wallet": name,
                "coldkey": ss58,
                "free_tao": balance["free_tao"],
                "staked_tao": balance["staked_tao"],
                "positions": len(stakes),
                "stakes": [
                    {"netuid": position.netuid, "hotkey": position.hotkey, "stake": str(position.stake)}
                    for position in stakes
                ],
            }
        )
    return rows


async def wallet_inspect_data(
    client: Client, name: str, coldkey_ss58: str
) -> dict[str, object]:
    """Detailed wallet view in one connection with parallel reads."""
    free, stakes, delegated, identity = await asyncio.gather(
        client.balances.get(coldkey_ss58),
        client.read("stake_for_coldkey", coldkey_ss58=coldkey_ss58),
        client.read("delegated", coldkey_ss58=coldkey_ss58),
        client.read("identity", coldkey_ss58=coldkey_ss58),
    )
    balance = _wallet_balance_row(name, coldkey_ss58, free, _staked_from_positions(stakes))
    return {
        "balance": balance,
        "stake_positions": len(stakes),
        "stakes": stakes,
        "delegated": delegated,
        "identity": identity,
    }


async def query_storage(
    client: Client, module: str, storage: str, params: Optional[list] = None
) -> object:
    """Read storage not yet covered by generated descriptors."""
    block_hash = await client._substrate.block_hash()
    return await client._substrate.query(module, storage, params, block_hash=block_hash)


async def query_storage_map(
    client: Client, module: str, storage: str, params: Optional[list] = None
) -> list[tuple[object, object]]:
    """Read a storage map by pallet/function name."""
    block_hash = await client._substrate.block_hash()
    return await client._substrate.query_map(module, storage, params, block_hash=block_hash)


async def runtime_api(
    client: Client, api: str, method: str, params: list
) -> object:
    """Call a runtime API by name (for APIs missing from generated descriptors)."""
    block_hash = await client._substrate.block_hash()
    return await client._substrate.runtime_call(api, method, params, block_hash=block_hash)
