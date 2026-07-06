"""Declarative typed reads — the read-side analogue of intents.

Each read is a small function registered by a stable name. It is built on the
generic accessors (``client.query`` / ``client.runtime``) over the *generated*
descriptors, and applies the one bit metadata can't express: units and domain
typing (the "units map"). Reads are dispatchable by name (``client.read``) and
catalog-able for agents (``client.reads``), exactly like intents are for writes.

Aggregations (all-of-a-coldkey's stake) and computed values live here as fetch
functions; single scalar reads are one query plus a cast. Adding a read is a
few lines here, and it inherits the dispatch + catalog + CLI `query` command.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from ._generated import runtime_apis as api
from ._generated import storage as st
from .balance import Balance
from .settings import U16_MAX


@dataclass
class StakePosition:
    """One (coldkey, hotkey, netuid) stake position; ``stake`` is alpha (TAO on netuid 0)."""

    hotkey: str
    coldkey: str
    netuid: int
    stake: Balance
    is_registered: bool


@dataclass
class DelegateInfo:
    """A delegate hotkey: who owns it, its take, and where it is registered."""

    hotkey: str
    owner: str
    take: float  # fraction of emissions kept by the delegate, 0..1
    nominators: int
    registrations: list[int]
    validator_permits: list[int]
    return_per_1000: Balance
    total_daily_return: Balance


@dataclass
class DelegatedStake:
    """One nomination: stake a coldkey has delegated to a hotkey on a subnet."""

    delegate: DelegateInfo
    netuid: int
    stake: Balance


@dataclass
class Commitment:
    """On-chain commitment published by a hotkey on a subnet."""

    block: int
    deposit: Balance
    data: str  # committed bytes, utf-8 if possible, else 0x-hex
    fields: list  # raw decoded field variants, for non-Raw commitments


@dataclass
class SwapQuote:
    """Simulated swap result: what you'd receive, the fee, and slippage."""

    tao: Balance  # TAO-side amount
    alpha: Balance  # alpha-side amount (tagged with the subnet)
    tao_fee: Balance
    alpha_fee: Balance
    tao_slippage: Balance
    alpha_slippage: Balance


@dataclass
class ReadSpec:
    name: str
    doc: str
    params: dict[str, str]  # param name -> JSON type, for the catalog/CLI
    fetch: Callable[..., Awaitable[Any]]


REGISTRY: dict[str, ReadSpec] = {}


def read(name: str, params: Optional[dict[str, str]] = None):
    """Register a read under a stable machine name."""

    def decorate(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        if name in REGISTRY:
            raise ValueError(f"Duplicate read: {name}")
        doc = (fn.__doc__ or "").strip().split("\n")[0]
        REGISTRY[name] = ReadSpec(name, doc, params or {}, fn)
        return fn

    return decorate


def list_reads() -> list[dict[str, Any]]:
    """Machine-readable catalog of every read (for agents / the CLI)."""
    return [
        {"name": s.name, "description": s.doc, "params": s.params}
        for s in sorted(REGISTRY.values(), key=lambda s: s.name)
    ]


# --- Aggregations / runtime-API reads -------------------------------------


def _stake_position(r: dict) -> StakePosition:
    return StakePosition(
        hotkey=str(r["hotkey"]),
        coldkey=str(r["coldkey"]),
        netuid=int(r["netuid"]),
        stake=Balance.from_rao(int(r["stake"]), int(r["netuid"])),
        is_registered=bool(r["is_registered"]),
    )


@read("stake_for_coldkey", {"coldkey_ss58": "string"})
async def stake_for_coldkey(client, coldkey_ss58: str) -> list[StakePosition]:
    """Every stake position held by a coldkey, across all hotkeys and subnets."""
    records = await client.runtime(
        api.StakeInfoRuntimeApi.get_stake_info_for_coldkey, [coldkey_ss58]
    )
    return [_stake_position(r) for r in records or []]


@read("stake_for_coldkeys", {"coldkey_ss58s": "array"})
async def stake_for_coldkeys(client, coldkey_ss58s: list[str]) -> dict[str, list[StakePosition]]:
    """Every stake position for several coldkeys at once, in one runtime call."""
    records = await client.runtime(
        api.StakeInfoRuntimeApi.get_stake_info_for_coldkeys, [coldkey_ss58s]
    )
    return {
        str(coldkey): [_stake_position(r) for r in positions or []]
        for coldkey, positions in records or []
    }


@read("quote_stake", {"netuid": "integer", "amount_tao": "number"})
async def quote_stake(client, netuid: int, amount_tao: float) -> SwapQuote:
    """Simulate staking ``amount_tao`` TAO into a subnet: alpha out, fee, and slippage.

    Use this to compute a safe ``limit_price_rao`` for the ``add_stake_limit`` intent.
    """
    rao = Balance.from_tao(amount_tao).rao
    r = await client.runtime(
        api.SwapRuntimeApi.sim_swap_tao_for_alpha, {"netuid": netuid, "tao": rao}
    )
    return _swap_quote(r, netuid)


@read("quote_unstake", {"netuid": "integer", "amount_alpha": "number"})
async def quote_unstake(client, netuid: int, amount_alpha: float) -> SwapQuote:
    """Simulate unstaking ``amount_alpha`` alpha from a subnet: TAO out, fee, and slippage."""
    rao = Balance.from_tao(amount_alpha, netuid).rao
    r = await client.runtime(
        api.SwapRuntimeApi.sim_swap_alpha_for_tao, {"netuid": netuid, "alpha": rao}
    )
    return _swap_quote(r, netuid)


def _swap_quote(r: dict, netuid: int) -> SwapQuote:
    return SwapQuote(
        tao=Balance.from_rao(int(r["tao_amount"])),
        alpha=Balance.from_rao(int(r["alpha_amount"]), netuid),
        tao_fee=Balance.from_rao(int(r["tao_fee"])),
        alpha_fee=Balance.from_rao(int(r["alpha_fee"]), netuid),
        tao_slippage=Balance.from_rao(int(r["tao_slippage"])),
        alpha_slippage=Balance.from_rao(int(r["alpha_slippage"]), netuid),
    )


@read("children", {"hotkey_ss58": "string", "netuid": "integer"})
async def children(client, hotkey_ss58: str, netuid: int) -> list[tuple[int, str]]:
    """Child hotkeys of a parent on a subnet, as (proportion, child_ss58) pairs."""
    entries = await client.query(st.SubtensorModule.ChildKeys, [hotkey_ss58, netuid])
    return [(int(prop), str(child)) for prop, child in entries or []]


@read("parents", {"hotkey_ss58": "string", "netuid": "integer"})
async def parents(client, hotkey_ss58: str, netuid: int) -> list[tuple[int, str]]:
    """Parent hotkeys of a child on a subnet, as (proportion, parent_ss58) pairs."""
    entries = await client.query(st.SubtensorModule.ParentKeys, [hotkey_ss58, netuid])
    return [(int(prop), str(parent)) for prop, parent in entries or []]


# --- Delegates -------------------------------------------------------------


def _delegate_info(d: dict) -> DelegateInfo:
    return DelegateInfo(
        hotkey=str(d["delegate_ss58"]),
        owner=str(d["owner_ss58"]),
        take=int(d["take"]) / U16_MAX,
        nominators=len(d.get("nominators") or []),
        registrations=[int(n) for n in d.get("registrations") or []],
        validator_permits=[int(n) for n in d.get("validator_permits") or []],
        return_per_1000=Balance.from_rao(int(d.get("return_per_1000") or 0)),
        total_daily_return=Balance.from_rao(int(d.get("total_daily_return") or 0)),
    )


@read("delegates", {})
async def delegates(client) -> list[DelegateInfo]:
    """Every delegate hotkey on the network, with take and registrations."""
    records = await client.runtime(api.DelegateInfoRuntimeApi.get_delegates, [])
    return [_delegate_info(d) for d in records or []]


@read("delegate", {"hotkey_ss58": "string"})
async def delegate(client, hotkey_ss58: str) -> Optional[DelegateInfo]:
    """Delegate info for one hotkey, or None if it is not a delegate."""
    record = await client.runtime(api.DelegateInfoRuntimeApi.get_delegate, [hotkey_ss58])
    return _delegate_info(record) if record else None


@read("is_delegate", {"hotkey_ss58": "string"})
async def is_delegate(client, hotkey_ss58: str) -> bool:
    """Whether a hotkey is a delegate."""
    record = await client.runtime(api.DelegateInfoRuntimeApi.get_delegate, [hotkey_ss58])
    return record is not None


@read("delegate_take", {"hotkey_ss58": "string"})
async def delegate_take(client, hotkey_ss58: str) -> dict:
    """A hotkey's delegate take (emission fraction it keeps) with the allowed min/max."""
    raw, lo, hi = await asyncio.gather(
        client.query(st.SubtensorModule.Delegates, [hotkey_ss58]),
        client.query(st.SubtensorModule.MinDelegateTake),
        client.query(st.SubtensorModule.MaxDelegateTake),
    )
    return {
        "hotkey": hotkey_ss58,
        "take": int(raw or 0) / U16_MAX,
        "take_u16": int(raw or 0),
        "min": int(lo or 0) / U16_MAX,
        "max": int(hi or 0) / U16_MAX,
    }


@read("delegated", {"coldkey_ss58": "string"})
async def delegated(client, coldkey_ss58: str) -> list[DelegatedStake]:
    """Every nomination a coldkey holds: (delegate, netuid, stake) per position."""
    records = await client.runtime(api.DelegateInfoRuntimeApi.get_delegated, [coldkey_ss58])
    return [
        DelegatedStake(
            delegate=_delegate_info(info),
            netuid=int(netuid),
            stake=Balance.from_rao(int(stake), int(netuid)),
        )
        for info, (netuid, stake) in records or []
    ]


# --- Commitments -----------------------------------------------------------


def _decode_commitment_data(fields: list) -> str:
    """Concatenate Raw* field bytes; utf-8 when possible, else 0x-hex."""
    data = b""
    for entry in fields:
        for variant, value in (entry or {}).items():
            if variant.startswith("Raw") and isinstance(value, str):
                data += bytes.fromhex(value.removeprefix("0x"))
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return "0x" + data.hex()


@read("commitment", {"netuid": "integer", "hotkey_ss58": "string"})
async def commitment(client, netuid: int, hotkey_ss58: str) -> Optional[Commitment]:
    """The commitment a hotkey has published on a subnet, or None."""
    record = await client.query(st.Commitments.CommitmentOf, [netuid, hotkey_ss58])
    if not record:
        return None
    fields = list((record.get("info") or {}).get("fields") or [])
    return Commitment(
        block=int(record.get("block") or 0),
        deposit=Balance.from_rao(int(record.get("deposit") or 0)),
        data=_decode_commitment_data(fields),
        fields=fields,
    )


@read("revealed_commitment", {"netuid": "integer", "hotkey_ss58": "string"})
async def revealed_commitment(client, netuid: int, hotkey_ss58: str) -> Any:
    """The revealed (timelock-decrypted) commitment for a hotkey on a subnet, or None."""
    return await client.query(st.Commitments.RevealedCommitments, [netuid, hotkey_ss58])


@read("subnet_hyperparameters", {"netuid": "integer"})
async def subnet_hyperparameters(client, netuid: int) -> dict:
    """All hyperparameters for a subnet (named fields; version-dependent set)."""
    return await client.runtime(api.SubnetInfoRuntimeApi.get_subnet_hyperparams, [netuid])


@read("metagraph", {"netuid": "integer"})
async def metagraph(client, netuid: int) -> dict:
    """The full metagraph for a subnet in one call (stakes, ranks, emissions, axons, ...)."""
    return await client.runtime(api.SubnetInfoRuntimeApi.get_metagraph, [netuid])


# --- Proxies ---------------------------------------------------------------


@read("proxies", {"coldkey_ss58": "string"})
async def proxies(client, coldkey_ss58: str) -> dict:
    """Proxy delegations of an account: who may sign on its behalf, and the reserved deposit."""
    value = await client.query(st.Proxy.Proxies, [coldkey_ss58])
    delegations, deposit = value or ([], 0)
    return {
        "proxies": [
            {
                "delegate": str(d["delegate"]),
                "proxy_type": str(d["proxy_type"]),
                "delay": int(d["delay"]),
            }
            for d in delegations
        ],
        "deposit": Balance.from_rao(int(deposit)),
    }


# --- Coldkey swap / identity ------------------------------------------------


def _utf8(value: Any) -> Any:
    """Decode chain byte-strings (hex or bytes) to text where possible."""
    if isinstance(value, str) and value.startswith("0x"):
        value = bytes.fromhex(value[2:])
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return "0x" + bytes(value).hex()
    return value


@read("coldkey_swap_announcement", {"coldkey_ss58": "string"})
async def coldkey_swap_announcement(client, coldkey_ss58: str) -> Optional[dict]:
    """A coldkey's pending swap announcement (execute block, new-key hash, disputed), or None.

    This is the ``swap-check`` status: ``ColdkeySwapAnnouncements`` stores the block
    at which the swap becomes executable and the BlakeTwo256 hash committed to.
    """
    value, disputed = await asyncio.gather(
        client.query(st.SubtensorModule.ColdkeySwapAnnouncements, [coldkey_ss58]),
        client.query(st.SubtensorModule.ColdkeySwapDisputes, [coldkey_ss58]),
    )
    if not value:
        return None
    execute_block, new_coldkey_hash = value
    return {
        "execute_block": int(execute_block),
        "new_coldkey_hash": str(new_coldkey_hash),
        "disputed": bool(disputed),
        "dispute_block": int(disputed) if disputed else None,
    }


@read("identity", {"coldkey_ss58": "string"})
async def identity(client, coldkey_ss58: str) -> Optional[dict]:
    """The on-chain identity of a coldkey (name, links, description), or None."""
    value = await client.query(st.SubtensorModule.IdentitiesV2, [coldkey_ss58])
    return {k: _utf8(v) for k, v in value.items()} if value else None


@read("subnet_identity", {"netuid": "integer"})
async def subnet_identity(client, netuid: int) -> Optional[dict]:
    """The identity metadata of a subnet, or None."""
    value = await client.query(st.SubtensorModule.SubnetIdentitiesV3, [netuid])
    return {k: _utf8(v) for k, v in value.items()} if value else None


@read("associated_evm_key", {"netuid": "integer", "uid": "integer"})
async def associated_evm_key(client, netuid: int, uid: int) -> Optional[dict]:
    """The EVM address associated with a neuron (by netuid + uid) and the block it was set."""
    value = await client.query(st.SubtensorModule.AssociatedEvmAddress, [netuid, uid])
    if not value:
        return None
    evm_address, block = value
    return {"evm_address": str(evm_address), "block": int(block)}


@read("root_claim_type", {"coldkey_ss58": "string"})
async def root_claim_type(client, coldkey_ss58: str) -> dict:
    """How a coldkey claims root alpha emission: Swap, Keep, or KeepSubnets(+subnets)."""
    value = await client.query(st.SubtensorModule.RootClaimType, [coldkey_ss58])
    if isinstance(value, dict):
        (variant, payload), *_ = value.items()
        subnets = None
        if isinstance(payload, dict) and payload.get("subnets") is not None:
            subnets = [int(n) for n in payload["subnets"]]
        return {"type": str(variant), "subnets": subnets}
    return {"type": str(value), "subnets": None}


@read("auto_stake", {"coldkey_ss58": "string", "netuid": "integer"})
async def auto_stake(client, coldkey_ss58: str, netuid: int) -> Optional[str]:
    """The hotkey a coldkey auto-stakes its rewards to on a subnet, or None if unset."""
    value = await client.query(st.SubtensorModule.AutoStakeDestination, [coldkey_ss58, netuid])
    return str(value) if value else None


@read("multisig", {"account_ss58": "string", "call_hash": "string"})
async def multisig(client, account_ss58: str, call_hash: str) -> Optional[dict]:
    """A pending multisig operation (opening timepoint, approvals, depositor), or None."""
    ch = call_hash if call_hash.startswith("0x") else "0x" + call_hash
    value = await client.query(st.Multisig.Multisigs, [account_ss58, ch])
    if not value:
        return None
    when = value.get("when") or {}
    return {
        "timepoint": {"height": int(when.get("height", 0)), "index": int(when.get("index", 0))},
        "deposit": Balance.from_rao(int(value.get("deposit") or 0)),
        "depositor": str(value.get("depositor")),
        "approvals": [str(a) for a in value.get("approvals") or []],
    }


# --- Subnet leases ----------------------------------------------------------


def _lease(lease_id: Any, v: dict) -> dict:
    end = v.get("end_block")
    return {
        "lease_id": int(lease_id),
        "beneficiary": str(v["beneficiary"]),
        "coldkey": str(v["coldkey"]),
        "hotkey": str(v["hotkey"]),
        "emissions_share": int(v["emissions_share"]),  # percent 0..100
        "end_block": int(end) if end is not None else None,
        "netuid": int(v["netuid"]),
        "cost": Balance.from_rao(int(v["cost"])),
    }


@read("lease", {"lease_id": "integer"})
async def lease(client, lease_id: int) -> Optional[dict]:
    """A subnet lease by id (beneficiary, emissions share, end block, netuid, cost), or None."""
    value = await client.query(st.SubtensorModule.SubnetLeases, [lease_id])
    return _lease(lease_id, value) if value else None


@read("leases", {})
async def leases(client) -> list[dict]:
    """Every subnet lease on the network."""
    entries = await client.query_map(st.SubtensorModule.SubnetLeases)
    return [_lease(k, v) for k, v in entries]


@read("mev_shield_next_key", {})
async def mev_shield_next_key(client) -> Optional[str]:
    """The MEV Shield ML-KEM-768 public key (0x-hex) used to encrypt shielded txs, or None."""
    value = await client.query(st.MevShield.NextKey)
    if not value:
        return None
    return value if isinstance(value, str) else "0x" + bytes(value).hex()


# --- Crowdloans -------------------------------------------------------------


@read("crowdloan", {"crowdloan_id": "integer"})
async def crowdloan(client, crowdloan_id: int) -> Optional[dict]:
    """A crowdloan's state (creator, deposit, raised, cap, end, target/call), or None."""
    value = await client.query(st.Crowdloan.Crowdloans, [crowdloan_id])
    if not value:
        return None
    target = value.get("target_address")
    return {
        "creator": str(value.get("creator")),
        "deposit": Balance.from_rao(int(value.get("deposit") or 0)),
        "min_contribution": Balance.from_rao(int(value.get("min_contribution") or 0)),
        "cap": Balance.from_rao(int(value.get("cap") or 0)),
        "raised": Balance.from_rao(int(value.get("raised") or 0)),
        "end": int(value.get("end") or 0),
        "finalized": bool(value.get("finalized")),
        "target_address": str(target) if target else None,
        "funds_account": str(value.get("funds_account")) if value.get("funds_account") else None,
    }


# --- Ownership / registration reads ---------------------------------------


@read("hotkey_owner", {"hotkey_ss58": "string"})
async def hotkey_owner(client, hotkey_ss58: str) -> Optional[str]:
    """The coldkey that owns a hotkey, or None if unowned."""
    value = await client.query(st.SubtensorModule.Owner, [hotkey_ss58])
    return str(value) if value else None


@read("uid", {"hotkey_ss58": "string", "netuid": "integer"})
async def uid(client, hotkey_ss58: str, netuid: int) -> Optional[int]:
    """UID of a hotkey on a subnet, or None if not registered there."""
    value = await client.query(st.SubtensorModule.Uids, [netuid, hotkey_ss58])
    return None if value is None else int(value)


# --- Locks / conviction ----------------------------------------------------


@read("coldkey_lock", {"coldkey_ss58": "string", "netuid": "integer"})
async def coldkey_lock(client, coldkey_ss58: str, netuid: int) -> Optional[dict]:
    """Lock state for a coldkey on a subnet, or None if no lock exists."""
    value = await client.runtime(
        api.StakeInfoRuntimeApi.get_coldkey_lock, [coldkey_ss58, netuid]
    )
    if not value:
        return None
    return {
        "hotkey": str(value.get("hotkey")),
        "netuid": int(value.get("netuid", netuid)),
        "locked_alpha": Balance.from_rao(int(value.get("locked") or 0), netuid),
        "is_perpetual": bool(value.get("is_perpetual")),
    }


@read("hotkey_conviction", {"hotkey_ss58": "string", "netuid": "integer"})
async def hotkey_conviction(client, hotkey_ss58: str, netuid: int) -> dict:
    """Conviction metrics for a hotkey on a subnet."""
    value = await client.runtime(
        api.StakeInfoRuntimeApi.get_hotkey_conviction, [hotkey_ss58, netuid]
    )
    return value if isinstance(value, dict) else {"value": value}


@read("most_convicted_hotkey", {"netuid": "integer"})
async def most_convicted_hotkey(client, netuid: int) -> Optional[str]:
    """Hotkey with the highest conviction on a subnet, if any."""
    value = await client.runtime(
        api.StakeInfoRuntimeApi.get_most_convicted_hotkey_on_subnet, [netuid]
    )
    return str(value) if value else None


@read("alpha_price", {"netuid": "integer"})
async def alpha_price(client, netuid: int) -> Balance:
    """Current alpha price for a subnet (TAO per alpha, as a Balance)."""
    rao = await client.runtime(api.SwapRuntimeApi.current_alpha_price, [netuid])
    return Balance.from_rao(int(rao), netuid)


@read("subnet_start_schedule", {"netuid": "integer"})
async def subnet_start_schedule(client, netuid: int) -> dict:
    """When a registered subnet can call ``start_call``."""
    from .._generated import constants

    registered_at = await client.query(st.SubtensorModule.NetworkRegisteredAt, [netuid])
    delay = int(await client.constant(constants.SubtensorModule.InitialStartCallDelay))
    registered_block = int(registered_at or 0)
    return {
        "netuid": netuid,
        "registered_at": registered_block,
        "start_call_delay": delay,
        "earliest_start_block": registered_block + delay,
        "current_block": await client.block(),
    }


@read("mechanism_count", {"netuid": "integer"})
async def mechanism_count(client, netuid: int) -> int:
    """Current mechanism count configured for a subnet."""
    value = await client.query(st.SubtensorModule.MechanismCountCurrent, [netuid])
    return int(value or 0)


@read("mechanism_emission_split", {"netuid": "integer"})
async def mechanism_emission_split(client, netuid: int) -> list[int]:
    """Emission split between mechanisms on a subnet."""
    value = await client.query(st.SubtensorModule.MechanismEmissionSplit, [netuid])
    return [int(x) for x in (value or [])]


@read("crowdloans", {})
async def crowdloans(client) -> list[dict]:
    """All crowdloans on chain (id and summary fields)."""
    rows = await client.query_map(st.Crowdloan.Crowdloans)
    out: list[dict] = []
    for crowdloan_id, value in rows:
        if not value:
            continue
        out.append(
            {
                "id": int(crowdloan_id),
                "creator": str(value.get("creator")),
                "raised_tao": Balance.from_rao(int(value.get("raised") or 0)).tao,
                "cap_tao": Balance.from_rao(int(value.get("cap") or 0)).tao,
                "finalized": bool(value.get("finalized")),
            }
        )
    return sorted(out, key=lambda row: row["id"])


@read("crowdloan_contributors", {"crowdloan_id": "integer"})
async def crowdloan_contributors(client, crowdloan_id: int) -> list[dict]:
    """Contributors and amounts for a crowdloan."""
    rows = await client.query_map(st.Crowdloan.Contributions, [crowdloan_id])
    return [
        {
            "contributor": str(contributor),
            "amount_tao": Balance.from_rao(int(amount or 0)).tao,
        }
        for contributor, amount in rows
    ]


@read("auto_stake_all", {"coldkey_ss58": "string"})
async def auto_stake_all(client, coldkey_ss58: str) -> list[dict]:
    """Every auto-stake destination configured for a coldkey."""
    rows = await client.query_map(st.SubtensorModule.AutoStakeDestination)
    out: list[dict] = []
    for (coldkey, netuid), hotkey in rows:
        if str(coldkey) != coldkey_ss58:
            continue
        out.append({"netuid": int(netuid), "hotkey": str(hotkey)})
    return sorted(out, key=lambda row: row["netuid"])


@read("subnet_registration_cost", {})
async def subnet_registration_cost(client) -> Balance:
    """Current cost to register a new subnet."""
    rao = await client.runtime(api.SubnetRegistrationRuntimeApi.get_network_registration_cost, [])
    return Balance.from_rao(int(rao))


# --- Rate limits / timing / economics (scalar storage + cast) -------------


def _scalar_read(name: str, item, *, per_netuid: bool, doc: str):
    params = {"netuid": "integer"} if per_netuid else {}

    async def fetch(client, netuid: Optional[int] = None) -> int:
        keys = [netuid] if per_netuid else None
        return int(await client.query(item, keys))

    fetch.__doc__ = doc
    read(name, params)(fetch)


_scalar_read(
    "weights_rate_limit",
    st.SubtensorModule.WeightsSetRateLimit,
    per_netuid=True,
    doc="Blocks a hotkey must wait between weight sets on a subnet.",
)
_scalar_read(
    "tx_rate_limit",
    st.SubtensorModule.TxRateLimit,
    per_netuid=False,
    doc="Global transaction rate limit in blocks.",
)
_scalar_read(
    "difficulty",
    st.SubtensorModule.Difficulty,
    per_netuid=True,
    doc="Current PoW registration difficulty for a subnet.",
)
_scalar_read(
    "min_allowed_weights",
    st.SubtensorModule.MinAllowedWeights,
    per_netuid=True,
    doc="Minimum number of weights a validator must set on a subnet.",
)
_scalar_read(
    "max_weight_limit",
    st.SubtensorModule.MaxWeightsLimit,
    per_netuid=True,
    doc="Maximum allowed value for any single weight (u16) on a subnet.",
)
_scalar_read(
    "immunity_period",
    st.SubtensorModule.ImmunityPeriod,
    per_netuid=True,
    doc="Blocks a newly registered neuron is immune from deregistration.",
)
_scalar_read(
    "reveal_period",
    st.SubtensorModule.RevealPeriodEpochs,
    per_netuid=True,
    doc="Commit-reveal reveal window, in epochs, for a subnet.",
)
