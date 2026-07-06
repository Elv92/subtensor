"""`subtensor subnets`: list subnets and inspect one."""

from __future__ import annotations

from typing import Optional

import typer

from ..._generated import storage
from ...intents import BurnedRegister, RegisterSubnet, SetSubnetIdentity, StartCall, UpdateSymbol
from ..context import AppContext, address_cli_name, ctx_of
from ..globals import with_globals

app = typer.Typer(no_args_is_help=True, help="Inspect subnets.")


@app.command("list")
@with_globals
def list_subnets(ctx: typer.Context):
    """List all subnets with tempo, burn, and neuron count."""
    app_ctx: AppContext = ctx_of(ctx)

    infos = app_ctx.run(lambda client: client.subnets.all())
    rows = [[i.netuid, i.tempo, i.burn, i.neuron_count] for i in infos]
    records = [
        {
            "netuid": i.netuid,
            "tempo": i.tempo,
            "burn_tao": i.burn.tao,
            "neurons": i.neuron_count,
        }
        for i in infos
    ]
    app_ctx.output.table("subnets", ["netuid", "tempo", "burn", "neurons"], rows, records)


@app.command()
@with_globals
def show(
    ctx: typer.Context,
    netuid: int = typer.Argument(..., help="Subnet netuid."),
):
    """Show details for a single subnet."""
    app_ctx: AppContext = ctx_of(ctx)

    async def _op(client):
        if not await client.query(storage.SubtensorModule.NetworksAdded, [netuid]):
            return None
        return await client.subnets.info(netuid)

    info = app_ctx.run(_op)
    if info is None:
        app_ctx.output.error(f"subnet {netuid} does not exist")
        raise typer.Exit(1)
    app_ctx.output.detail(
        f"subnet {info.netuid}",
        {
            "tempo": info.tempo,
            "burn": info.burn,
            "neurons": info.neuron_count,
        },
    )


@app.command("hyperparameters")
@with_globals
def hyperparameters(
    ctx: typer.Context,
    netuid: int = typer.Argument(..., help="Subnet netuid."),
):
    """Show subnet hyperparameters."""
    app_ctx: AppContext = ctx_of(ctx)
    params = app_ctx.run(lambda c: c.read("subnet_hyperparameters", netuid=netuid))
    app_ctx.output.detail(f"hyperparameters {netuid}", params)


@app.command("burn-cost")
@with_globals
def burn_cost(ctx: typer.Context):
    """Show current subnet registration cost."""
    app_ctx: AppContext = ctx_of(ctx)
    cost = app_ctx.run(lambda c: c.read("subnet_registration_cost"))
    app_ctx.output.detail(None, {"burn_cost": cost, "tao": cost.tao})


@app.command("price")
@with_globals
def subnet_price(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
):
    """Show current alpha price for a subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    price = app_ctx.run(lambda c: c.read("alpha_price", netuid=netuid))
    app_ctx.output.detail(None, {"netuid": netuid, "price": str(price), "tao": price.tao})


@app.command("conviction")
@with_globals
def subnet_conviction(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58")),
):
    """Show conviction for a hotkey or the most-convicted hotkey on a subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    if hotkey_ss58:
        hotkey = app_ctx.resolve_address("hotkey_ss58", hotkey_ss58)
        data = app_ctx.run(lambda c: c.read("hotkey_conviction", hotkey_ss58=hotkey, netuid=netuid))
    else:

        async def _leader_conviction(client):
            leader = await client.read("most_convicted_hotkey", netuid=netuid)
            if not leader:
                return {"most_convicted_hotkey": None}
            conviction = await client.read(
                "hotkey_conviction", hotkey_ss58=leader, netuid=netuid
            )
            return {"most_convicted_hotkey": leader, "conviction": conviction}

        data = app_ctx.run(_leader_conviction)
    app_ctx.output.detail(f"conviction netuid {netuid}", data)


@app.command("check-start")
@with_globals
def check_start(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
):
    """Show when a subnet can call start_call."""
    app_ctx: AppContext = ctx_of(ctx)
    schedule = app_ctx.run(lambda c: c.read("subnet_start_schedule", netuid=netuid))
    app_ctx.output.detail(f"start schedule netuid {netuid}", schedule)


@app.command("start")
@with_globals
def start_subnet(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
):
    """Start a registered subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(StartCall(netuid=netuid))


@app.command("set-symbol")
@with_globals
def set_symbol(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    symbol: str = typer.Option(..., "--symbol"),
):
    """Update a subnet symbol."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(UpdateSymbol(netuid=netuid, symbol=symbol))


@app.command("register")
@with_globals
def register_subnet(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58")),
):
    """Register a hotkey on a subnet by burning TAO."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(BurnedRegister(netuid=netuid, hotkey_ss58=hotkey_ss58))


@app.command("get-identity")
@with_globals
def get_subnet_identity(
    ctx: typer.Context,
    netuid: int = typer.Argument(...),
):
    """Show subnet identity metadata."""
    app_ctx: AppContext = ctx_of(ctx)
    identity = app_ctx.run(lambda c: c.read("subnet_identity", netuid=netuid))
    app_ctx.output.detail(f"subnet identity {netuid}", identity)


@app.command("set-identity")
@with_globals
def set_subnet_identity(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    name: str = typer.Option(..., "--name"),
    url: str = typer.Option("", "--url"),
    description: str = typer.Option("", "--description"),
):
    """Set subnet identity metadata (subnet owner)."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        SetSubnetIdentity(
            netuid=netuid,
            subnet_name=name,
            subnet_url=url,
            description=description,
        )
    )


@app.command("create")
@with_globals
def create_subnet(ctx: typer.Context):
    """Register a new subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(RegisterSubnet())


@app.command("metagraph")
@with_globals
def metagraph(
    ctx: typer.Context,
    netuid: int = typer.Argument(..., help="Subnet netuid."),
):
    """Show metagraph data for a subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    graph = app_ctx.run(lambda c: c.read("metagraph", netuid=netuid))
    app_ctx.output.detail(f"metagraph {netuid}", graph if isinstance(graph, dict) else {"data": graph})
