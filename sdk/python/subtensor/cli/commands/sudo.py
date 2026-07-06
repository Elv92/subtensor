"""`subtensor sudo`: subnet-owner hyperparameters and governance."""

from __future__ import annotations

from typing import Optional

import typer

from ...intents import (
    SenateVote,
    SetHyperparameter,
    SetMechanismCount,
    SetMechanismEmissionSplit,
    SetTake,
    StakeBurn,
    TrimSubnet,
)
from ..context import AppContext, address_cli_name, ctx_of, ss58_param_help
from ..globals import with_globals
from ..helpers import query_storage

app = typer.Typer(no_args_is_help=True, help="Subnet-owner config and governance.")


@app.command("set")
@with_globals
def sudo_set(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    name: str = typer.Option(..., "--name", help="Hyperparameter name."),
    value: int = typer.Option(..., "--value"),
):
    """Set an owner-settable subnet hyperparameter."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(SetHyperparameter(netuid=netuid, name=name, value=value))


@app.command("get")
@with_globals
def sudo_get(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
):
    """Show subnet hyperparameters."""
    app_ctx: AppContext = ctx_of(ctx)
    params = app_ctx.run(lambda c: c.read("subnet_hyperparameters", netuid=netuid))
    app_ctx.output.detail(f"hyperparameters netuid {netuid}", params)


@app.command("senate")
@with_globals
def senate_members(ctx: typer.Context):
    """List senate member hotkeys."""
    app_ctx: AppContext = ctx_of(ctx)

    async def _op(client):
        try:
            return await query_storage(client, "SenateMembers", "Members")
        except Exception:
            return await query_storage(client, "Triumvirate", "Members")

    members = app_ctx.run(_op)
    app_ctx.output.detail("senate members", {"members": members})


@app.command("proposals")
@with_globals
def proposals(ctx: typer.Context):
    """List active governance proposals."""
    app_ctx: AppContext = ctx_of(ctx)

    async def _op(client):
        try:
            return await query_storage(client, "Triumvirate", "Proposals")
        except Exception as error:
            raise ValueError(f"could not read proposals: {error}") from error

    props = app_ctx.run(_op)
    app_ctx.output.detail("proposals", {"proposals": props})


@app.command("senate-vote")
@with_globals
def senate_vote(
    ctx: typer.Context,
    proposal_hash: str = typer.Option(..., "--proposal-hash", help="0x-hex proposal hash."),
    index: int = typer.Option(..., "--index"),
    approve: bool = typer.Option(True, "--approve/--reject"),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Cast a senate vote on a proposal."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        SenateVote(
            hotkey_ss58=hotkey_ss58,
            proposal_hash=proposal_hash,
            index=index,
            approve=approve,
        )
    )


@app.command("get-take")
@with_globals
def get_take(
    ctx: typer.Context,
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Show the delegate take for a hotkey."""
    app_ctx: AppContext = ctx_of(ctx)
    hotkey = app_ctx.resolve_address("hotkey_ss58", hotkey_ss58)
    take = app_ctx.run(lambda c: c.read("delegate_take", hotkey_ss58=hotkey))
    app_ctx.output.detail(None, {"hotkey": hotkey, "take": take})


@app.command("set-take")
@with_globals
def set_take(
    ctx: typer.Context,
    take: int = typer.Option(..., "--take", help="Take as u16 proportion."),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Set delegate take (delegates to tx set-take)."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(SetTake(take=take, hotkey_ss58=hotkey_ss58))


@app.command("trim")
@with_globals
def trim_subnet(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    max_n: int = typer.Option(..., "--max-n", help="Maximum UIDs to keep."),
):
    """Trim a subnet to at most max_n UIDs."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(TrimSubnet(netuid=netuid, max_n=max_n))


@app.command("stake-burn")
@with_globals
def stake_burn(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    amount: float = typer.Option(..., "--amount", help="TAO amount."),
    limit_price: int = typer.Option(..., "--limit-price"),
    hotkey_ss58: Optional[str] = typer.Option(None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")),
):
    """Execute a stake-burn (buyback) extrinsic."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        StakeBurn(
            netuid=netuid,
            amount_tao=amount,
            limit_price=limit_price,
            hotkey_ss58=hotkey_ss58,
        )
    )


mechanisms_app = typer.Typer(no_args_is_help=True, help="Subnet mechanism configuration.")
app.add_typer(mechanisms_app, name="mechanisms")


@mechanisms_app.command("count")
@with_globals
def mechanism_count(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    value: Optional[int] = typer.Option(None, "--value", help="Set count when provided."),
):
    """Get or set mechanism count."""
    app_ctx: AppContext = ctx_of(ctx)
    if value is None:
        count = app_ctx.run(lambda c: c.read("mechanism_count", netuid=netuid))
        app_ctx.output.detail(None, {"netuid": netuid, "mechanism_count": count})
        return
    app_ctx.submit(SetMechanismCount(netuid=netuid, mechanism_count=value))


@mechanisms_app.command("emissions")
@with_globals
def mechanism_emissions(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
):
    """Show mechanism emission split."""
    app_ctx: AppContext = ctx_of(ctx)
    split = app_ctx.run(lambda c: c.read("mechanism_emission_split", netuid=netuid))
    app_ctx.output.detail(None, {"netuid": netuid, "split": split})


@mechanisms_app.command("split-emissions")
@with_globals
def set_mechanism_emissions(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    split: str = typer.Option(..., "--split", help="Comma-separated emission split values."),
):
    """Set mechanism emission split."""
    app_ctx: AppContext = ctx_of(ctx)
    values = [int(part.strip()) for part in split.split(",") if part.strip()]
    app_ctx.submit(SetMechanismEmissionSplit(netuid=netuid, split=values))
