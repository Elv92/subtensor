"""The `subtensor call` command — the raw-call escape hatch, as a CLI command.

Every generated call builder (``subtensor.calls``) is reachable here by its
``Pallet.function`` name, so any extrinsic the chain exposes — including ones no
intent wraps, like ``Sudo.sudo`` or ``System.set_code`` — can be submitted from
the command line. This is the CLI projection of ``client.submit_call``: ``tx`` is
for the safe, previewable intents; ``call`` is the deliberate escape hatch.

A runtime upgrade is the canonical example (the sudo key signs)::

    subtensor call System.set_code --args-file runtime.json --sudo --yes

where ``runtime.json`` is ``{"code": "0x<compact-wasm-hex>"}``. ``--sudo`` wraps
the call in ``Sudo.sudo(...)``; drop it to submit the call directly.

When finney's sudo key is a multisig, save contacts once::

    subtensor addresses triumph-a 5OtherA...
    subtensor addresses triumph-b 5OtherB...
    subtensor config add-multisig --name finney-sudo --threshold 2 \\
      --signatories suro,triumph-a,triumph-b

Then each signatory approves with the short form::

    subtensor call System.set_code --args-file runtime.json --sudo \\
      --multisig finney-sudo -w suro --yes

After the first approval, the CLI prints ``call_hash``, ``call_data``, ``timepoint``,
and copy-paste commands for each remaining co-signer.

If you only know the *other* signers' addresses, pass them and your wallet is
added automatically::

    subtensor call System.set_code --args-file runtime.json --sudo \\
      --multisig-threshold 2 --other-signatories 5OtherA...,5OtherB... \\
      -w suro --yes
"""

from __future__ import annotations

import json
import shlex
from typing import Any, Optional

import typer

from .. import calls
from .. import config as cfg
from .._generated import storage as st
from .context import ctx_of
from .globals import with_globals

_MAX_SHOWN = 80  # truncate long param values (e.g. a wasm blob) in dry-run output


def _resolve_builder(target: str):
    """Resolve a ``Pallet.function`` name to its generated call builder."""
    pallet_name, sep, function = target.partition(".")
    if not sep or not function:
        raise typer.BadParameter(f"expected Pallet.function, got {target!r}", param_hint="TARGET")
    pallet = getattr(calls, pallet_name, None)
    if pallet is None or not isinstance(pallet, type):
        raise typer.BadParameter(f"unknown pallet {pallet_name!r}", param_hint="TARGET")
    builder = getattr(pallet, function, None)
    if not callable(builder):
        raise typer.BadParameter(
            f"unknown call {function!r} in pallet {pallet_name!r}", param_hint="TARGET"
        )
    return builder


def _load_params(args: Optional[str], args_file: Optional[str]) -> dict:
    """Load call parameters from a JSON string or file into a dict."""
    if args and args_file:
        raise typer.BadParameter("pass either --args or --args-file, not both")
    raw = None
    if args_file:
        try:
            with open(args_file) as handle:
                raw = handle.read()
        except OSError as error:
            raise typer.BadParameter(
                f"cannot read {args_file!r}: {error}", param_hint="--args-file"
            )
    elif args:
        raw = args
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise typer.BadParameter(f"invalid JSON: {error}")
    if not isinstance(parsed, dict):
        raise typer.BadParameter("call parameters must be a JSON object (name -> value)")
    return parsed


def _for_display(params: dict) -> dict[str, Any]:
    """Truncate long string values so a dry-run of e.g. set_code stays readable."""
    shown: dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str) and len(value) > _MAX_SHOWN:
            shown[key] = f"{value[:_MAX_SHOWN]}… (+{len(value) - _MAX_SHOWN} chars)"
        else:
            shown[key] = value
    return shown


def _parse_signatory_list(app_ctx, raw: str, *, param: str) -> list[str]:
    """Comma-separated signatories (ss58, address-book name, wallet) -> resolved addresses."""
    try:
        return app_ctx.resolve_signatory_list(raw)
    except ValueError as error:
        raise typer.BadParameter(str(error), param_hint=param)


def _resolve_multisig(
    app_ctx,
    *,
    multisig_name: Optional[str],
    threshold: Optional[int],
    signatories: Optional[str],
    other_signatories: Optional[str],
    signer: str,
) -> tuple[Optional[int], list[str], Optional[str]]:
    """Resolve multisig settings from a preset name or inline flags."""
    inline = threshold is not None or signatories or other_signatories
    if multisig_name and inline:
        raise typer.BadParameter(
            "use either --multisig NAME or inline multisig flags, not both",
            param_hint="--multisig",
        )
    if multisig_name:
        entry = cfg.get_multisig(multisig_name)
        if entry is None:
            raise typer.BadParameter(
                f"unknown multisig {multisig_name!r}; run `subtensor config multisigs`",
                param_hint="--multisig",
            )
        return (
            entry["threshold"],
            _resolve_stored_signatories(app_ctx, entry["signatories"]),
            multisig_name,
        )
    if threshold is None:
        return None, [], None
    if threshold < 1:
        raise typer.BadParameter("threshold must be >= 1", param_hint="--multisig-threshold")
    if signatories and other_signatories:
        raise typer.BadParameter(
            "pass either --signatories or --other-signatories, not both",
            param_hint="--signatories",
        )
    if signatories:
        sigs = _parse_signatory_list(app_ctx, signatories, param="--signatories")
    elif other_signatories:
        sigs = _parse_signatory_list(app_ctx, other_signatories, param="--other-signatories")
        wallet = app_ctx.wallet()
        self_addr = (
            wallet.coldkeypub.ss58_address if signer == "coldkey" else wallet.hotkey.ss58_address
        )
        sigs = list(dict.fromkeys(sigs + [self_addr]))
    else:
        raise typer.BadParameter(
            "with --multisig-threshold, pass --signatories or --other-signatories",
            param_hint="--multisig-threshold",
        )
    return threshold, sigs, None


def _resolve_stored_signatories(app_ctx, refs: list[str]) -> list[str]:
    """Resolve a saved multisig signer list (ss58, book names, or wallets)."""
    resolved: list[str] = []
    for ref in refs:
        address = app_ctx.resolve_address("coldkey_ss58", ref)
        if not address:
            raise typer.BadParameter(
                f"cannot resolve signatory {ref!r} in multisig preset",
                param_hint="--multisig",
            )
        resolved.append(address)
    return list(dict.fromkeys(resolved))


def _hex_bytes(value: bytes | str) -> str:
    if isinstance(value, bytes):
        return "0x" + value.hex()
    text = str(value)
    return text if text.startswith("0x") else "0x" + text


def _signatory_labels(app_ctx, refs: list[str]) -> dict[str, str]:
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


def _build_replay_command(
    app_ctx,
    *,
    target: str,
    params: dict,
    args_file: Optional[str],
    sudo: bool,
    preset: Optional[str],
    threshold: int,
    signatories: list[str],
    wallet_label: str,
    signer_role: str,
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
    if preset:
        parts.append(f"--multisig {shlex.quote(preset)}")
    else:
        parts.append(f"--multisig-threshold {threshold}")
        parts.append(f"--signatories {shlex.quote(','.join(signatories))}")
    parts.append(f"-w {shlex.quote(wallet_label)}")
    if signer_role != "coldkey":
        parts.append(f"--signer {signer_role}")
    parts.append("--yes")
    return " \\\n  ".join(parts)


async def _multisig_followup(
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
) -> dict[str, Any]:
    """Build co-signer instructions from on-chain multisig state after an approval."""
    call_hash = _hex_bytes(composed.call_hash)
    call_data = _hex_bytes(composed.data)
    pending = await client.query(st.Multisig.Multisigs, [ms.address, call_hash])
    labels = _signatory_labels(app_ctx, signatory_refs)

    if not pending:
        return {
            "status": "executed",
            "call_hash": call_hash,
            "call_data": call_data,
            "multisig_address": ms.address,
            "multisig_preset": preset,
        }

    when = pending.get("when") or {}
    timepoint = {
        "height": int(when.get("height", 0)),
        "index": int(when.get("index", 0)),
    }
    approvals = [str(a) for a in pending.get("approvals") or []]
    remaining = [s for s in signatories if s not in approvals]
    co_signer_commands = []
    for ss58 in remaining:
        label = labels.get(ss58, ss58)
        co_signer_commands.append(
            {
                "ss58": ss58,
                "label": label,
                "command": _build_replay_command(
                    app_ctx,
                    target=target,
                    params=params,
                    args_file=args_file,
                    sudo=sudo,
                    preset=preset,
                    threshold=threshold,
                    signatories=signatories,
                    wallet_label=label if label != ss58 else ss58,
                    signer_role=signer_role,
                ),
            }
        )

    return {
        "status": "pending",
        "approvals": len(approvals),
        "threshold": threshold,
        "call_hash": call_hash,
        "call_data": call_data,
        "timepoint": timepoint,
        "timepoint_display": f"{timepoint['height']}:{timepoint['index']}",
        "multisig_address": ms.address,
        "multisig_preset": preset,
        "approvals_so_far": approvals,
        "remaining_signatories": remaining,
        "co_signer_commands": co_signer_commands,
    }


@with_globals
def call(
    ctx: typer.Context,
    target: str = typer.Argument(
        ..., metavar="TARGET", help="The call as Pallet.function, e.g. System.set_code."
    ),
    args: Optional[str] = typer.Option(
        None, "--args", help='Call parameters as a JSON object, e.g. \'{"code": "0x.."}\'.'
    ),
    args_file: Optional[str] = typer.Option(
        None, "--args-file", help="Read the JSON parameters from a file (for large payloads)."
    ),
    sudo: bool = typer.Option(
        False, "--sudo", help="Wrap the call in Sudo.sudo (the signing key must be sudo)."
    ),
    multisig: Optional[str] = typer.Option(
        None,
        "--multisig",
        help="Named signer set from `subtensor config add-multisig` (replaces inline flags).",
    ),
    multisig_threshold: Optional[int] = typer.Option(
        None,
        "--multisig-threshold",
        help="Dispatch via a multisig: approvals needed before the call executes.",
    ),
    signatories: Optional[str] = typer.Option(
        None,
        "--signatories",
        help="Full signer set: ss58, address-book names, or wallet names (include yourself).",
    ),
    other_signatories: Optional[str] = typer.Option(
        None,
        "--other-signatories",
        help="Other signers only (book names or ss58); your -w wallet coldkey is added.",
    ),
    signer: str = typer.Option(
        "coldkey", "--signer", help="Which wallet key signs: 'coldkey' or 'hotkey'."
    ),
):
    """Submit any raw chain call (escape hatch; use `tx` for wrapped intents)."""
    app_ctx = ctx_of(ctx)
    if signer not in ("coldkey", "hotkey"):
        raise typer.BadParameter("must be 'coldkey' or 'hotkey'", param_hint="--signer")
    threshold, sigs, preset = _resolve_multisig(
        app_ctx,
        multisig_name=multisig,
        threshold=multisig_threshold,
        signatories=signatories,
        other_signatories=other_signatories,
        signer=signer,
    )
    builder = _resolve_builder(target)
    params = _load_params(args, args_file)
    signing = app_ctx.signer(signer)
    label = target + (" via Sudo.sudo" if sudo else "")
    via_multisig = threshold is not None
    if via_multisig and len(sigs) < threshold:
        raise typer.BadParameter(
            f"need at least {threshold} signatories, got {len(sigs)}",
            param_hint="--signatories",
        )

    async def prepare(client):
        """Build (and, for sudo, nest) the call against live metadata."""
        inner = builder(**params)
        if sudo:
            return calls.Sudo.sudo(call=await client.compose(inner))
        return inner

    if app_ctx.dry_run:
        fields: dict[str, Any] = {
            "target": target,
            "sudo": sudo,
            "signer": signer,
            "params": _for_display(params),
        }
        if via_multisig:

            async def _dry_run_multisig(client):
                await _compose_only(client, prepare)
                return await _multisig_address(client, sigs, threshold)

            ms_addr = app_ctx.run(_dry_run_multisig)
            fields["multisig_threshold"] = threshold
            fields["signatories"] = sigs
            fields["multisig_address"] = ms_addr
            if preset:
                fields["multisig_preset"] = preset
        else:
            app_ctx.run(lambda client: _compose_only(client, prepare))
        app_ctx.output.detail("dry run: raw call", fields)
        return

    if via_multisig:
        who = preset or f"{threshold}-of-{len(sigs)}"
        prompt = f"multisig-approve {label} ({who}, signed by {signer})?"
        success_msg = f"multisig approved {label}"
    else:
        prompt = f"submit raw call {label} (signed by {signer})?"
        success_msg = f"submitted {label}"

    app_ctx.confirm(prompt)
    if via_multisig:
        if preset:
            signatory_refs = cfg.get_multisig(preset)["signatories"]
        elif signatories:
            signatory_refs = [part.strip() for part in signatories.split(",") if part.strip()]
        elif other_signatories:
            signatory_refs = [
                part.strip() for part in other_signatories.split(",") if part.strip()
            ] + [app_ctx.wallet_name]
        else:
            signatory_refs = sigs

        async def _submit_multisig(client):
            ms = await client.multisig(sigs, threshold)
            call = await prepare(client)
            composed = await client.compose(call)
            result = await ms.approve(call, signing, signer=signer)
            followup = await _multisig_followup(
                client,
                app_ctx,
                composed=composed,
                ms=ms,
                signatories=sigs,
                threshold=threshold,
                signatory_refs=signatory_refs,
                target=target,
                params=params,
                args_file=args_file,
                sudo=sudo,
                preset=preset,
                signer_role=signer,
            )
            result.data["multisig_followup"] = followup
            return result

        result = app_ctx.run(_submit_multisig)
    else:
        result = app_ctx.run(lambda client: _submit(client, prepare, signing, signer))
    if not app_ctx.output.result(result, success_msg):
        raise typer.Exit(1)


async def _compose_only(client, prepare):
    """Build and compose the call to validate its params against chain metadata."""
    return await client.compose(await prepare(client))


async def _multisig_address(client, signatories, threshold):
    """Derive the on-chain multisig account address for a signer set."""
    ms = await client.multisig(signatories, threshold)
    return ms.address


async def _submit(client, prepare, wallet, signer):
    return await client.submit_call(await prepare(client), wallet, signer=signer)
