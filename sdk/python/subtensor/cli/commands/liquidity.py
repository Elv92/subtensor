"""`subtensor liquidity`: swap-pallet liquidity positions."""

from __future__ import annotations

from typing import Optional

import typer

from ...intents import AddLiquidity, ModifyLiquidity, RemoveLiquidity
from ..context import AppContext, address_cli_name, ctx_of, ss58_param_help
from ..globals import with_globals
from ..helpers import query_storage_map

app = typer.Typer(no_args_is_help=True, help="Manage liquidity positions.")


@app.command("list")
@with_globals
def list_positions(
    ctx: typer.Context,
    netuid: Optional[int] = typer.Option(None, "--netuid"),
    coldkey_ss58: Optional[str] = typer.Option(None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")),
):
    """List liquidity positions (reads Swap.Positions storage)."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)

    async def _op(client):
        try:
            rows = await query_storage_map(client, "Swap", "Positions")
        except Exception as error:
            raise ValueError(f"could not read liquidity positions: {error}") from error
        out = []
        for key, value in rows:
            if not isinstance(key, (list, tuple)) or len(key) < 2:
                continue
            nid, coldkey = int(key[0]), str(key[1])
            if coldkey != owner:
                continue
            if netuid is not None and nid != netuid:
                continue
            out.append({"netuid": nid, "coldkey": coldkey, "position": value})
        return out

    positions = app_ctx.run(_op)
    if not positions:
        app_ctx.output.detail("liquidity positions", {"count": 0, "positions": []})
        return
    rows = [[p["netuid"], p.get("position")] for p in positions]
    app_ctx.output.table("liquidity positions", ["netuid", "position"], rows, positions)


@app.command("add")
@with_globals
def add_liquidity(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    tick_low: int = typer.Option(..., "--tick-low"),
    tick_high: int = typer.Option(..., "--tick-high"),
    liquidity: int = typer.Option(..., "--liquidity", help="Liquidity amount (rao units)."),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Add liquidity to a tick range."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        AddLiquidity(
            netuid=netuid,
            tick_low=tick_low,
            tick_high=tick_high,
            liquidity=liquidity,
            hotkey_ss58=hotkey_ss58,
        )
    )


@app.command("modify")
@with_globals
def modify_liquidity(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    position_id: int = typer.Option(..., "--position-id"),
    delta: int = typer.Option(..., "--delta", help="Liquidity delta (negative to remove)."),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Modify liquidity in an existing position."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        ModifyLiquidity(
            netuid=netuid,
            position_id=position_id,
            liquidity_delta=delta,
            hotkey_ss58=hotkey_ss58,
        )
    )


@app.command("remove")
@with_globals
def remove_liquidity(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    position_id: int = typer.Option(..., "--position-id"),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Remove an entire liquidity position."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        RemoveLiquidity(netuid=netuid, position_id=position_id, hotkey_ss58=hotkey_ss58)
    )
