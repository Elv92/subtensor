"""`subtensor balance`: query free TAO."""

from __future__ import annotations

from typing import Optional

import typer

from ..context import AppContext, ctx_of, ss58_param_help
from ..globals import with_globals
from ..helpers import list_coldkeys, wallet_balance_row, wallet_balance_rows

app = typer.Typer(no_args_is_help=True, help="Query balances.")


@app.command()
@with_globals
def show(
    ctx: typer.Context,
    address: Optional[str] = typer.Argument(
        None,
        help="Coldkey ss58 address or a local wallet name. "
        "Defaults to the configured wallet's coldkey.",
    ),
    all_wallets: bool = typer.Option(
        False, "--all", "-a", help="Show balances for every wallet under --wallet-path."
    ),
    sort_by: Optional[str] = typer.Option(
        None, "--sort", help="When using --all: name, free, staked, or total."
    ),
):
    """Show free, staked, and total TAO balance for one or all wallets."""
    app_ctx: AppContext = ctx_of(ctx)
    if all_wallets:
        coldkeys = list_coldkeys(app_ctx.wallet_path)
        if not coldkeys:
            app_ctx.output.error(f"no wallets found in {app_ctx.wallet_path}")
            raise typer.Exit(1)

        async def _all(client):
            return await wallet_balance_rows(client, coldkeys)

        rows_data = app_ctx.run(_all)
        if sort_by:
            key_map = {
                "name": lambda r: r["wallet"].lower(),
                "free": lambda r: r["free_tao"],
                "staked": lambda r: r["staked_tao"],
                "total": lambda r: r["total_tao"],
            }
            if sort_by not in key_map:
                app_ctx.output.error(f"unknown sort key {sort_by!r}; use: name, free, staked, total")
                raise typer.Exit(1)
            reverse = sort_by != "name"
            rows_data.sort(key=key_map[sort_by], reverse=reverse)
        table_rows = [
            [r["wallet"], r["coldkey"], r["free"], r["staked"], r["total"]] for r in rows_data
        ]
        app_ctx.output.table(
            "wallet balances",
            ["wallet", "coldkey", "free", "staked", "total"],
            table_rows,
            rows_data,
        )
        return

    resolved = app_ctx.resolve_address("coldkey_ss58", address)
    row = app_ctx.run(lambda client: wallet_balance_row(client, app_ctx.wallet_name, resolved))
    app_ctx.output.detail(None, row)
