"""`subtensor lock`: stake-lock and conviction commands."""

from __future__ import annotations

import asyncio
from typing import Optional

import typer

from ...intents import LockStake, MoveLock, SetPerpetualLock
from ..context import AppContext, address_cli_name, ctx_of, ss58_param_help
from ..globals import with_globals

app = typer.Typer(no_args_is_help=True, help="Stake-lock and conviction.")


@app.command("list")
@with_globals
def list_locks(
    ctx: typer.Context,
    coldkey_ss58: Optional[str] = typer.Option(None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")),
    netuid: Optional[int] = typer.Option(None, "--netuid"),
):
    """List lock state for a coldkey (optionally filtered by netuid)."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)

    async def _op(client):
        if netuid is not None:
            return [
                await client.read("coldkey_lock", coldkey_ss58=owner, netuid=netuid)
            ]
        stakes = await client.read("stake_for_coldkey", coldkey_ss58=owner)
        netuids = sorted({position.netuid for position in stakes})
        return await asyncio.gather(
            *[
                client.read("coldkey_lock", coldkey_ss58=owner, netuid=nid)
                for nid in netuids
            ]
        )

    locks = app_ctx.run(_op)
    if netuid is not None:
        lock = locks[0]
        app_ctx.output.detail(f"lock netuid {netuid}", lock or {"status": "no lock"})
        return

    rows = []
    records = []
    for lock in locks:
        if not lock:
            continue
        nid = lock["netuid"]
        rows.append([nid, lock.get("hotkey"), lock.get("locked_alpha"), lock.get("is_perpetual")])
        records.append({"netuid": nid, **lock})
    app_ctx.output.table("locks", ["netuid", "hotkey", "locked", "perpetual"], rows, records)


@app.command("show")
@with_globals
def show_lock(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    coldkey_ss58: Optional[str] = typer.Option(None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")),
):
    """Show detailed lock state for one subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)

    async def _op(client):
        lock = await client.read("coldkey_lock", coldkey_ss58=owner, netuid=netuid)
        if not lock:
            return {"lock": None, "conviction": None}
        conviction = await client.read(
            "hotkey_conviction", hotkey_ss58=lock["hotkey"], netuid=netuid
        )
        return {"lock": lock, "conviction": conviction}

    data = app_ctx.run(_op)
    app_ctx.output.detail(f"lock on netuid {netuid}", data)


@app.command("add")
@with_globals
def add_lock(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    amount: float = typer.Option(..., "--amount", help="Alpha amount to lock."),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
    perpetual: bool = typer.Option(False, "--perpetual", help="Enable perpetual lock mode first."),
):
    """Lock alpha stake on a subnet hotkey."""
    app_ctx: AppContext = ctx_of(ctx)
    if perpetual:
        app_ctx.submit(SetPerpetualLock(netuid=netuid, enabled=True))
    app_ctx.submit(LockStake(netuid=netuid, amount_alpha=amount, hotkey_ss58=hotkey_ss58))


@app.command("mode")
@with_globals
def lock_mode(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    perpetual: bool = typer.Option(..., "--perpetual/--decaying"),
):
    """Set perpetual or decaying lock mode for a subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(SetPerpetualLock(netuid=netuid, enabled=perpetual))


@app.command("move")
@with_globals
def move_lock(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    destination_hotkey_ss58: str = typer.Option(..., address_cli_name("destination_hotkey_ss58")),
):
    """Move an existing lock to a different hotkey."""
    app_ctx: AppContext = ctx_of(ctx)
    dest = app_ctx.resolve_address("hotkey_ss58", destination_hotkey_ss58)
    app_ctx.submit(MoveLock(netuid=netuid, destination_hotkey_ss58=dest))
