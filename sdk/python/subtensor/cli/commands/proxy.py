"""`subtensor proxy`: on-chain proxy account management."""

from __future__ import annotations

import json
from typing import Optional

import typer

from ...intents import AddProxy, CreatePureProxy, KillPureProxy, RemoveProxies, RemoveProxy
from ..context import AppContext, address_cli_name, ctx_of, ss58_param_help
from ..globals import with_globals

app = typer.Typer(no_args_is_help=True, help="On-chain proxy management.")


@app.command("create")
@with_globals
def create_proxy(
    ctx: typer.Context,
    proxy_type: str = typer.Option("Staking", "--proxy-type"),
    delay: int = typer.Option(0, "--delay"),
    index: int = typer.Option(0, "--index"),
):
    """Create a pure proxy account."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(CreatePureProxy(proxy_type=proxy_type, delay=delay, index=index))


@app.command("add")
@with_globals
def add_proxy(
    ctx: typer.Context,
    delegate_ss58: str = typer.Option(..., address_cli_name("delegate_ss58")),
    proxy_type: str = typer.Option("Staking", "--proxy-type"),
    delay: int = typer.Option(0, "--delay"),
):
    """Add a proxy delegate."""
    app_ctx: AppContext = ctx_of(ctx)
    delegate = app_ctx.resolve_address("coldkey_ss58", delegate_ss58)
    app_ctx.submit(AddProxy(delegate_ss58=delegate, proxy_type=proxy_type, delay=delay))


@app.command("remove")
@with_globals
def remove_proxy(
    ctx: typer.Context,
    delegate_ss58: str = typer.Option(..., address_cli_name("delegate_ss58")),
    proxy_type: str = typer.Option("Staking", "--proxy-type"),
    delay: int = typer.Option(0, "--delay"),
    all_proxies: bool = typer.Option(False, "--all", help="Remove every proxy at once."),
):
    """Remove a proxy delegate."""
    app_ctx: AppContext = ctx_of(ctx)
    if all_proxies:
        app_ctx.submit(RemoveProxies())
        return
    delegate = app_ctx.resolve_address("coldkey_ss58", delegate_ss58)
    app_ctx.submit(RemoveProxy(delegate_ss58=delegate, proxy_type=proxy_type, delay=delay))


@app.command("kill")
@with_globals
def kill_proxy(
    ctx: typer.Context,
    spawner_ss58: str = typer.Option(..., address_cli_name("spawner_ss58")),
    proxy_type: str = typer.Option("Staking", "--proxy-type"),
    index: int = typer.Option(0, "--index"),
    height: int = typer.Option(0, "--height"),
    ext_index: int = typer.Option(0, "--ext-index"),
):
    """Kill a pure proxy account."""
    app_ctx: AppContext = ctx_of(ctx)
    spawner = app_ctx.resolve_address("coldkey_ss58", spawner_ss58)
    app_ctx.submit(
        KillPureProxy(
            spawner_ss58=spawner,
            proxy_type=proxy_type,
            index=index,
            height=height,
            ext_index=ext_index,
        )
    )


@app.command("execute")
@with_globals
def execute_announced(
    ctx: typer.Context,
    delegate_ss58: str = typer.Option(..., address_cli_name("delegate_ss58")),
    real_ss58: str = typer.Option(..., address_cli_name("real_ss58")),
    inner_op: str = typer.Option(..., "--inner-op", help="Intent op name for the inner call."),
    inner_args: str = typer.Option("{}", "--inner-args", help="JSON object of inner intent args."),
    force_proxy_type: Optional[str] = typer.Option(None, "--force-proxy-type"),
):
    """Execute a previously announced proxy call."""
    app_ctx: AppContext = ctx_of(ctx)
    delegate = app_ctx.resolve_address("coldkey_ss58", delegate_ss58)
    real = app_ctx.resolve_address("coldkey_ss58", real_ss58)
    try:
        args = json.loads(inner_args)
    except json.JSONDecodeError as error:
        app_ctx.output.error(f"invalid --inner-args JSON: {error}")
        raise typer.Exit(1)
    from ...intents import ExecuteProxyAnnounced

    app_ctx.submit(
        ExecuteProxyAnnounced(
            delegate_ss58=delegate,
            real_ss58=real,
            inner_op=inner_op,
            inner_args=args,
            force_proxy_type=force_proxy_type,
        )
    )
