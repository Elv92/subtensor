"""`subtensor utils`: conversion and connection helpers."""

from __future__ import annotations

import asyncio
import time

import typer

from ...balance import Balance
from ...settings import NETWORKS, resolve_endpoint
from ..context import AppContext, ctx_of
from ..globals import with_globals

app = typer.Typer(no_args_is_help=True, help="Utility commands.")


@app.command("convert")
@with_globals
def convert(
    ctx: typer.Context,
    amount: float = typer.Argument(..., help="Amount to convert."),
    from_rao: bool = typer.Option(False, "--rao", help="Input is rao; output TAO."),
    netuid: int = typer.Option(0, "--netuid", help="Subnet for alpha denomination."),
):
    """Convert between TAO and rao (or alpha units when netuid > 0)."""
    app_ctx: AppContext = ctx_of(ctx)
    if from_rao:
        value = Balance.from_rao(int(amount), netuid)
        app_ctx.output.detail(None, {"rao": int(amount), "amount": value.tao, "unit": str(value)})
    else:
        value = Balance.from_tao(amount, netuid)
        app_ctx.output.detail(None, {"tao": amount, "rao": value.rao, "unit": str(value)})


@app.command("latency")
@with_globals
def latency(
    ctx: typer.Context,
    networks: str = typer.Option("", "--networks", help="Comma-separated network names to test (default: all presets)."),
):
    """Measure websocket connection latency to network endpoints."""
    app_ctx: AppContext = ctx_of(ctx)
    names = [n.strip() for n in networks.split(",") if n.strip()] or sorted(NETWORKS)

    async def _probe(name: str) -> dict:
        label, endpoint = resolve_endpoint(name)
        start = time.perf_counter()
        try:
            from ...client import Client

            async with Client(label) as client:
                await client.block()
            ms = (time.perf_counter() - start) * 1000
            return {"network": label, "endpoint": endpoint, "latency_ms": round(ms, 1), "ok": True}
        except Exception as error:
            ms = (time.perf_counter() - start) * 1000
            return {
                "network": label,
                "endpoint": endpoint,
                "latency_ms": round(ms, 1),
                "ok": False,
                "error": str(error),
            }

    async def _all():
        return await asyncio.gather(*[_probe(name) for name in names])

    results = asyncio.run(_all())
    rows = [[r["network"], r["endpoint"], r["latency_ms"], r["ok"]] for r in results]
    app_ctx.output.table("latency", ["network", "endpoint", "ms", "ok"], rows, results)
