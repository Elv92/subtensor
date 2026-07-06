"""Shared multisig helpers for call submission and pending-op inspection."""

from __future__ import annotations

import asyncio
import json
import shlex
from typing import Any, Optional

from .. import config as cfg
from .._generated import storage as st
from .._transport.errors import BlockNotFound, StateDiscardedError, SubstrateRequestException
from ..result import ExtrinsicResult


def hex_bytes(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if hasattr(value, "hex") and not isinstance(value, str):
        return "0x" + bytes(value).hex()
    text = str(value)
    return text if text.startswith("0x") else "0x" + text


def signatory_labels(app_ctx, refs: list[str]) -> dict[str, str]:
    """Map ss58 addresses to short labels (preset ref, address-book name, or ss58)."""
    labels: dict[str, str] = {}
    for ref in refs:
        address = app_ctx.resolve_address("coldkey_ss58", ref)
        if address:
            labels[address] = ref
    for entry in cfg.load_addresses():
        address = entry.get("address")
        name = entry.get("name")
        if address and name and address not in labels:
            labels[str(address)] = str(name)
    return labels


def build_replay_command(
    app_ctx,
    *,
    target: str,
    params: dict,
    args_file: Optional[str],
    sudo: bool,
    threshold: int,
    signatories: list[str],
    wallet_label: str,
    signer_role: str = "coldkey",
) -> str:
    """Build a copy-paste ``subtensor call`` command for a co-signer."""
    parts = ["subtensor"]
    if app_ctx.network != "finney":
        parts.append(f"-n {shlex.quote(app_ctx.network)}")
    parts.append(f"call {target}")
    if args_file:
        parts.append(f"--args-file {shlex.quote(args_file)}")
    elif params:
        parts.append(f"--args {shlex.quote(json.dumps(params, separators=(',', ':')))}")
    if sudo:
        parts.append("--sudo")
    parts.append(f"--multisig-threshold {threshold}")
    parts.append(f"--signatories {shlex.quote(','.join(signatories))}")
    parts.append(f"-w {shlex.quote(wallet_label)}")
    if signer_role != "coldkey":
        parts.append(f"--signer {signer_role}")
    parts.append("--yes")
    return " ".join(parts)


def resolve_multisig_preset(app_ctx, name: str) -> tuple[int, list[str], list[str]]:
    """Return threshold, resolved ss58 signatories, and preset refs."""
    entry = cfg.get_multisig(name)
    if entry is None:
        raise ValueError(f"unknown multisig {name!r}")
    refs = list(entry["signatories"])
    signatories: list[str] = []
    for ref in refs:
        address = app_ctx.resolve_address("coldkey_ss58", ref)
        if not address:
            raise ValueError(f"cannot resolve signatory {ref!r} in multisig preset")
        signatories.append(address)
    signatories = list(dict.fromkeys(signatories))
    return int(entry["threshold"]), signatories, refs


def _json_friendly(value: Any) -> Any:
    if hasattr(value, "value"):
        value = value.value
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, dict):
        return {str(k): _json_friendly(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_friendly(v) for v in value]
    return value


def _call_spec_from_decoded(raw_call: Any) -> Optional[dict[str, Any]]:
    value = raw_call.value if hasattr(raw_call, "value") else raw_call
    if not isinstance(value, dict):
        return None
    module = value.get("call_module")
    function = value.get("call_function")
    args = {
        str(arg.get("name")): _json_friendly(arg.get("value"))
        for arg in (value.get("call_args") or [])
        if arg.get("name") is not None
    }
    if module == "Sudo" and function == "sudo":
        inner = args.pop("call", None)
        if inner is None:
            return None
        inner_spec = _call_spec_from_decoded(inner)
        if inner_spec is None:
            return None
        inner_spec["sudo"] = True
        return inner_spec
    if not module or not function:
        return None
    return {
        "target": f"{module}.{function}",
        "params": args,
        "sudo": False,
    }


async def decode_call_data(client, call_data: str) -> Optional[dict[str, Any]]:
    """Decode scale-encoded call bytes into target, params, and sudo flag."""
    try:
        raw = await client._substrate.raw.decode_scale("Call", call_data)
    except Exception:
        return None
    spec = _call_spec_from_decoded(raw)
    if spec is None:
        return None
    spec["call_data"] = hex_bytes(call_data)
    return spec


async def resolve_call_spec(
    client,
    *,
    call_hash: str,
    call_data: Optional[str] = None,
    timepoint: Optional[dict[str, int]] = None,
) -> Optional[dict[str, Any]]:
    """Resolve call target/params from cache, call_data hex, or opening extrinsic."""
    cached = cfg.get_multisig_cache(hex_bytes(call_hash))
    if cached:
        return cached
    if call_data:
        spec = await decode_call_data(client, call_data)
        if spec:
            spec["call_hash"] = hex_bytes(call_hash)
        return spec
    if timepoint:
        spec = await fetch_call_from_timepoint(
            client,
            height=int(timepoint["height"]),
            index=int(timepoint["index"]),
        )
        if spec is None:
            return None
        if spec.get("call_hash") and hex_bytes(spec["call_hash"]) != hex_bytes(call_hash):
            return None
        spec["call_hash"] = hex_bytes(call_hash)
        return spec
    return None


async def fetch_call_from_timepoint(
    client,
    *,
    height: int,
    index: int,
) -> Optional[dict[str, Any]]:
    """Recover a multisig inner call from the opening ``as_multi`` extrinsic."""
    try:
        block = await client._substrate.raw.get_block(block_number=height)
    except (StateDiscardedError, BlockNotFound):
        return None
    except SubstrateRequestException:
        return None
    if not block:
        return None
    extrinsics = block.get("extrinsics") or []
    if index < 0 or index >= len(extrinsics):
        return None
    extrinsic = extrinsics[index]
    value = extrinsic.value if hasattr(extrinsic, "value") else extrinsic
    outer = value.get("call") or {}
    if outer.get("call_module") != "Multisig":
        return None
    args = {arg.get("name"): arg.get("value") for arg in (outer.get("call_args") or [])}
    if outer.get("call_function") == "as_multi":
        inner = args.get("call")
        if inner is None:
            return None
        spec = _call_spec_from_decoded(inner)
        if spec is None:
            return None
        spec["call_data"] = hex_bytes(getattr(inner, "data", b""))
        if hasattr(inner, "call_hash"):
            spec["call_hash"] = hex_bytes(inner.call_hash)
        return spec
    if outer.get("call_function") == "approve_as_multi":
        return None
    return None


async def list_pending_multisig_ops(client, multisig_address: str) -> list[dict[str, Any]]:
    """All open multisig operations for ``multisig_address``."""
    ops: list[dict[str, Any]] = []
    for key, value in await client.query_map(st.Multisig.Multisigs):
        account = str(key[0]) if isinstance(key, (list, tuple)) else str(key)
        if account != multisig_address:
            continue
        call_hash = key[1] if isinstance(key, (list, tuple)) and len(key) > 1 else None
        if value is None:
            continue
        when = value.get("when") or {}
        approvals = [str(a) for a in value.get("approvals") or []]
        ops.append(
            {
                "call_hash": hex_bytes(call_hash),
                "timepoint": {
                    "height": int(when.get("height", 0)),
                    "index": int(when.get("index", 0)),
                },
                "timepoint_display": f"{int(when.get('height', 0))}:{int(when.get('index', 0))}",
                "depositor": str(value.get("depositor")),
                "deposit_rao": int(value.get("deposit") or 0),
                "approvals": approvals,
            }
        )
    return sorted(ops, key=lambda op: op["timepoint"]["height"], reverse=True)


def _event_payload(entry: Any) -> dict[str, Any]:
    record = entry.value if hasattr(entry, "value") else entry
    if not isinstance(record, dict):
        return {}
    event = record.get("event", record)
    return event if isinstance(event, dict) else {}


def _multisig_event_ids(events: list) -> set[str]:
    ids: set[str] = set()
    for entry in events or []:
        event = _event_payload(entry)
        if event.get("module_id") != "Multisig":
            continue
        event_id = event.get("event_id")
        if event_id:
            ids.add(str(event_id))
    return ids


def _multisig_executed(events: list) -> bool:
    return "MultisigExecuted" in _multisig_event_ids(events)


async def _query_pending_multisig(
    client,
    multisig_address: str,
    call_hash: str,
    *,
    raw_call_hash: Any = None,
    attempts: int = 6,
    delay_seconds: float = 0.5,
) -> Optional[dict[str, Any]]:
    """Read pending multisig state, retrying briefly after inclusion."""
    key_candidates: list[Any] = []
    if raw_call_hash is not None:
        key_candidates.append(raw_call_hash)
    key_candidates.append(hex_bytes(call_hash))

    for attempt in range(attempts):
        for key in key_candidates:
            pending = await client.query(st.Multisig.Multisigs, [multisig_address, key])
            if pending:
                return pending
        if attempt + 1 < attempts:
            await asyncio.sleep(delay_seconds)
    return None


async def build_pending_followup(
    client,
    app_ctx,
    *,
    ms,
    threshold: int,
    signatories: list[str],
    signatory_refs: list[str],
    call_hash: str,
    pending: dict[str, Any],
    preset: Optional[str] = None,
    call_spec: Optional[dict[str, Any]] = None,
    signer_role: str = "coldkey",
) -> dict[str, Any]:
    """Build a pending multisig record with optional co-signer commands."""
    labels = signatory_labels(app_ctx, signatory_refs)
    approvals = list(pending.get("approvals") or [])
    remaining = [s for s in signatories if s not in approvals]
    call_data = None
    target = None
    params: dict[str, Any] = {}
    args_file = None
    sudo = False
    if call_spec:
        target = call_spec.get("target")
        params = call_spec.get("params") or {}
        args_file = call_spec.get("args_file")
        sudo = bool(call_spec.get("sudo"))
        call_data = call_spec.get("call_data")

    co_signer_commands = []
    if target:
        for ss58 in remaining:
            label = labels.get(ss58, ss58)
            co_signer_commands.append(
                {
                    "ss58": ss58,
                    "label": label,
                    "command": build_replay_command(
                        app_ctx,
                        target=target,
                        params=params,
                        args_file=args_file,
                        sudo=sudo,
                        threshold=threshold,
                        signatories=signatories,
                        wallet_label=label if label != ss58 else ss58,
                        signer_role=signer_role,
                    ),
                }
            )

    return {
        "status": "pending",
        "target": target,
        "sudo": sudo,
        "params": params,
        "approvals": len(approvals),
        "threshold": threshold,
        "call_hash": hex_bytes(call_hash),
        "call_data": call_data,
        "timepoint": pending.get("timepoint"),
        "timepoint_display": pending.get("timepoint_display"),
        "multisig_address": ms.address,
        "multisig_preset": preset,
        "depositor": pending.get("depositor"),
        "depositor_label": labels.get(str(pending.get("depositor")), pending.get("depositor")),
        "approvals_so_far": approvals,
        "approval_labels": [labels.get(a, a) for a in approvals],
        "remaining_signatories": remaining,
        "remaining_labels": [labels.get(a, a) for a in remaining],
        "co_signer_commands": co_signer_commands,
        "commands_available": bool(co_signer_commands),
        "decode_hint": (
            None
            if co_signer_commands
            else (
                "Call details unknown. The opening block may be pruned on this RPC node, "
                "the op may have used approve_as_multi (hash only), or local cache may be missing. "
                "Pass --call-data 0x.. once, or re-open the op with a current SDK build."
            )
        ),
    }


async def multisig_followup_from_composed(
    client,
    app_ctx,
    *,
    composed,
    ms,
    signatories: list[str],
    threshold: int,
    signatory_refs: list[str],
    target: str,
    params: dict,
    args_file: Optional[str],
    sudo: bool,
    preset: Optional[str],
    signer_role: str,
    result: ExtrinsicResult,
) -> dict[str, Any]:
    """Build co-signer instructions after submitting a multisig approval."""
    call_hash = hex_bytes(composed.call_hash)
    call_data = hex_bytes(composed.data)
    call_spec = {
        "target": target,
        "params": params,
        "args_file": args_file,
        "sudo": sudo,
        "call_data": call_data,
        "call_hash": call_hash,
        "threshold": threshold,
        "signatories": signatories,
        "multisig_address": ms.address,
        "multisig_preset": preset,
        "network": app_ctx.network,
    }
    cfg.save_multisig_cache_entry(call_hash, call_spec)

    if _multisig_executed(result.events):
        return {
            "status": "executed",
            "target": target,
            "sudo": sudo,
            "call_hash": call_hash,
            "call_data": call_data,
            "multisig_address": ms.address,
            "multisig_preset": preset,
        }

    pending = await _query_pending_multisig(
        client,
        ms.address,
        call_hash,
        raw_call_hash=composed.call_hash,
    )
    if not pending:
        for row in await list_pending_multisig_ops(client, ms.address):
            if row["call_hash"] == call_hash:
                pending = {
                    "when": row["timepoint"],
                    "approvals": row["approvals"],
                    "depositor": row["depositor"],
                }
                break

    if not pending:
        if _multisig_event_ids(result.events):
            pending_row = {
                "approvals": [],
                "depositor": None,
                "timepoint": {"height": 0, "index": 0},
                "timepoint_display": "?",
            }
            followup = await build_pending_followup(
                client,
                app_ctx,
                ms=ms,
                threshold=threshold,
                signatories=signatories,
                signatory_refs=signatory_refs,
                call_hash=call_hash,
                pending=pending_row,
                preset=preset,
                call_spec=call_spec,
                signer_role=signer_role,
            )
            followup["decode_hint"] = (
                "Approval recorded on-chain but pending state is not visible yet. "
                "Run `subtensor sudo pending` to inspect co-signer commands."
            )
            return followup
        return {
            "status": "submitted",
            "target": target,
            "sudo": sudo,
            "call_hash": call_hash,
            "call_data": call_data,
            "multisig_address": ms.address,
            "multisig_preset": preset,
            "decode_hint": (
                "Approval submitted but pending state is not visible yet. "
                "Run `subtensor sudo pending` shortly to inspect co-signer commands."
            ),
        }

    when = pending.get("when") or {}
    pending_row = {
        "approvals": [str(a) for a in pending.get("approvals") or []],
        "depositor": str(pending.get("depositor")),
        "timepoint": {
            "height": int(when.get("height", 0)),
            "index": int(when.get("index", 0)),
        },
        "timepoint_display": f"{int(when.get('height', 0))}:{int(when.get('index', 0))}",
    }
    return await build_pending_followup(
        client,
        app_ctx,
        ms=ms,
        threshold=threshold,
        signatories=signatories,
        signatory_refs=signatory_refs,
        call_hash=call_hash,
        pending=pending_row,
        preset=preset,
        call_spec=call_spec,
        signer_role=signer_role,
    )


async def list_pending_with_commands(
    client,
    app_ctx,
    *,
    ms,
    threshold: int,
    signatories: list[str],
    signatory_refs: list[str],
    preset: Optional[str] = None,
    call_hash_filter: Optional[str] = None,
    call_data: Optional[str] = None,
) -> list[dict[str, Any]]:
    """List pending multisig ops with co-signer commands when call details are known."""
    rows = await list_pending_multisig_ops(client, ms.address)
    if call_hash_filter:
        wanted = hex_bytes(call_hash_filter)
        rows = [row for row in rows if row["call_hash"] == wanted]

    results: list[dict[str, Any]] = []
    for row in rows:
        data_override = None
        if call_data and call_hash_filter and row["call_hash"] == hex_bytes(call_hash_filter):
            data_override = call_data
        spec = await resolve_call_spec(
            client,
            call_hash=row["call_hash"],
            call_data=data_override,
            timepoint=row.get("timepoint"),
        )
        if spec and data_override:
            cfg.save_multisig_cache_entry(
                row["call_hash"],
                {
                    **spec,
                    "call_hash": row["call_hash"],
                    "threshold": threshold,
                    "signatories": signatories,
                    "multisig_address": ms.address,
                    "multisig_preset": preset,
                    "network": app_ctx.network,
                },
            )
        results.append(
            await build_pending_followup(
                client,
                app_ctx,
                ms=ms,
                threshold=threshold,
                signatories=signatories,
                signatory_refs=signatory_refs,
                call_hash=row["call_hash"],
                pending=row,
                preset=preset,
                call_spec=spec,
            )
        )
    return results
