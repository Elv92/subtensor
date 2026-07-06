"""`subtensor stake`: query and manage stake."""

from __future__ import annotations

import json
from typing import Optional

import typer

from ...intents import ClaimRoot, SetAutoStake, SetChildkeyTake, SetChildren, SetRootClaimType
from ..context import AppContext, address_cli_name, ctx_of, ss58_param_help
from ..globals import with_globals
from ..helpers import list_coldkeys

app = typer.Typer(no_args_is_help=True, help="Query and manage stake.")


@app.command()
@with_globals
def show(
    ctx: typer.Context,
    hotkey_ss58: Optional[str] = typer.Option(
        None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")
    ),
    netuid: int = typer.Option(..., "--netuid"),
    coldkey_ss58: Optional[str] = typer.Option(
        None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")
    ),
):
    """Show stake held by a coldkey on a hotkey within a subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    hotkey = app_ctx.resolve_address("hotkey_ss58", hotkey_ss58)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)
    stake = app_ctx.run(lambda c: c.staking.get(owner, hotkey, netuid))
    app_ctx.output.detail(
        None,
        {
            "coldkey": owner,
            "hotkey": hotkey,
            "netuid": netuid,
            "stake": stake,
            "alpha": stake.tao,
        },
    )


@app.command("list")
@with_globals
def stake_list(
    ctx: typer.Context,
    coldkey_ss58: Optional[str] = typer.Option(None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")),
    all_wallets: bool = typer.Option(False, "--all", "-a", help="List stake for every wallet."),
):
    """List all stake positions for a coldkey (or all wallets with --all)."""
    app_ctx: AppContext = ctx_of(ctx)
    if all_wallets:
        coldkeys = list_coldkeys(app_ctx.wallet_path)

        async def _all(client):
            ss58s = [ss58 for _, ss58 in coldkeys]
            return await client.read("stake_for_coldkeys", coldkey_ss58s=ss58s)

        grouped = app_ctx.run(_all)
        rows = []
        records = []
        for name, ss58 in coldkeys:
            for pos in grouped.get(ss58, []):
                rows.append([name, pos.netuid, pos.hotkey, pos.stake])
                records.append(
                    {
                        "wallet": name,
                        "coldkey": ss58,
                        "netuid": pos.netuid,
                        "hotkey": pos.hotkey,
                        "stake": str(pos.stake),
                    }
                )
        app_ctx.output.table("stake", ["wallet", "netuid", "hotkey", "stake"], rows, records)
        return

    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)
    positions = app_ctx.run(lambda c: c.read("stake_for_coldkey", coldkey_ss58=owner))
    rows = [[p.netuid, p.hotkey, p.stake, p.is_registered] for p in positions]
    records = [
        {"netuid": p.netuid, "hotkey": p.hotkey, "stake": str(p.stake), "registered": p.is_registered}
        for p in positions
    ]
    app_ctx.output.table("stake", ["netuid", "hotkey", "stake", "registered"], rows, records)


@app.command("auto")
@with_globals
def auto_stake_list(
    ctx: typer.Context,
    coldkey_ss58: Optional[str] = typer.Option(None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")),
):
    """List auto-stake destinations for a coldkey."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)
    rows = app_ctx.run(lambda c: c.read("auto_stake_all", coldkey_ss58=owner))
    if not rows:
        app_ctx.output.detail("auto-stake", {"destinations": []})
        return
    table_rows = [[r["netuid"], r["hotkey"]] for r in rows]
    app_ctx.output.table("auto-stake destinations", ["netuid", "hotkey"], table_rows, rows)


@app.command("set-auto")
@with_globals
def set_auto_stake(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Set auto-stake destination for a subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(SetAutoStake(netuid=netuid, hotkey_ss58=hotkey_ss58))


@app.command("set-claim")
@with_globals
def set_claim_type(
    ctx: typer.Context,
    claim_type: str = typer.Option(..., "--claim-type", help="Swap, Keep, or KeepSubnets."),
    subnets: Optional[str] = typer.Option(
        None, "--subnets", help="Comma-separated netuids (required for KeepSubnets)."
    ),
):
    """Set root claim type for the wallet coldkey."""
    app_ctx: AppContext = ctx_of(ctx)
    subnet_list = None
    if subnets:
        subnet_list = [int(part.strip()) for part in subnets.split(",") if part.strip()]
    app_ctx.submit(SetRootClaimType(claim_type=claim_type, subnets=subnet_list))


@app.command("process-claim")
@with_globals
def process_claim(
    ctx: typer.Context,
    subnets: str = typer.Option(..., "--subnets", help="Comma-separated netuids to claim from."),
):
    """Claim accumulated root dividends from subnets."""
    app_ctx: AppContext = ctx_of(ctx)
    subnet_list = [int(part.strip()) for part in subnets.split(",") if part.strip()]
    app_ctx.submit(ClaimRoot(subnets=subnet_list))


child_app = typer.Typer(no_args_is_help=True, help="Child hotkey delegation.")
app.add_typer(child_app, name="child")


@child_app.command("get")
@with_globals
def child_get(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Show child hotkeys assigned to a parent hotkey."""
    app_ctx: AppContext = ctx_of(ctx)
    hotkey = app_ctx.resolve_address("hotkey_ss58", hotkey_ss58)
    children = app_ctx.run(lambda c: c.read("children", hotkey_ss58=hotkey, netuid=netuid))
    app_ctx.output.detail("children", {"hotkey": hotkey, "netuid": netuid, "children": children})


@child_app.command("set")
@with_globals
def child_set(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    children: str = typer.Option(
        ...,
        "--children",
        help='JSON list of [proportion, hotkey_ss58] pairs, e.g. \'[[1000000,"5..."],]\'',
    ),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Assign child hotkeys with proportions."""
    app_ctx: AppContext = ctx_of(ctx)
    try:
        parsed = json.loads(children)
    except json.JSONDecodeError as error:
        app_ctx.output.error(f"invalid --children JSON: {error}")
        raise typer.Exit(1)
    app_ctx.submit(SetChildren(netuid=netuid, children=parsed, hotkey_ss58=hotkey_ss58))


@child_app.command("revoke")
@with_globals
def child_revoke(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Revoke all child hotkeys on a subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(SetChildren(netuid=netuid, children=[], hotkey_ss58=hotkey_ss58))


@child_app.command("take")
@with_globals
def child_take(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    take: int = typer.Option(..., "--take", help="Childkey take as u16 proportion."),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Set childkey take for a hotkey."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(SetChildkeyTake(netuid=netuid, take=take, hotkey_ss58=hotkey_ss58))


@app.command("wizard")
@with_globals
def stake_wizard(ctx: typer.Context):
    """Interactive stake movement guide (use `subtensor tx move-stake`, `transfer-stake`, or `swap-stake`)."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.output.detail(
        "stake wizard",
        {
            "move": "subtensor tx move-stake --origin-netuid N --destination-netuid M --amount X",
            "transfer": "subtensor tx transfer-stake --origin-hotkey H1 --destination-hotkey H2 ...",
            "swap": "subtensor tx swap-stake --origin-netuid N --destination-netuid M --amount X",
        },
    )
