"""`subtensor axon`: neuron serving endpoints."""

from __future__ import annotations

import typer

from ...intents import ResetAxon, ServeAxon, ServeAxonTls
from ..context import AppContext, ctx_of
from ..globals import with_globals

app = typer.Typer(no_args_is_help=True, help="Axon serving commands.")


@app.command("set")
@with_globals
def axon_set(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    ip: str = typer.Option(..., "--ip"),
    port: int = typer.Option(..., "--port"),
    tls: bool = typer.Option(False, "--tls"),
    certificate: str = typer.Option("", "--certificate", help="0x-hex TLS certificate (with --tls)."),
):
    """Publish an axon endpoint for the wallet hotkey."""
    app_ctx: AppContext = ctx_of(ctx)
    if tls:
        app_ctx.submit(ServeAxonTls(netuid=netuid, ip=ip, port=port, certificate=certificate))
    else:
        app_ctx.submit(ServeAxon(netuid=netuid, ip=ip, port=port))


@app.command("reset")
@with_globals
def axon_reset(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
):
    """Reset (stop serving) the wallet hotkey's axon on a subnet."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(ResetAxon(netuid=netuid))
