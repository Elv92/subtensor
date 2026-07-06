"""`subtensor weights`: commit-reveal weight commands."""

from __future__ import annotations

from typing import Optional

import typer

from ...intents import CommitWeights, RevealWeights, SetWeights
from ..context import AppContext, ctx_of
from ..globals import with_globals

app = typer.Typer(no_args_is_help=True, help="Validator weight commands.")


def _parse_int_list(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def _parse_float_list(raw: str) -> list[float]:
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


@app.command("set")
@with_globals
def set_weights(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    uids: str = typer.Option(..., "--uids", help="Comma-separated UIDs."),
    weights: str = typer.Option(..., "--weights", help="Comma-separated weights."),
    mechid: int = typer.Option(0, "--mechid"),
    version_key: int = typer.Option(0, "--version-key"),
):
    """Set validator weights directly (plaintext subnets)."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        SetWeights(
            netuid=netuid,
            uids=_parse_int_list(uids),
            weights=_parse_float_list(weights),
            mechid=mechid,
            version_key=version_key,
        )
    )


@app.command("commit")
@with_globals
def commit_weights(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    uids: str = typer.Option(..., "--uids"),
    weights: str = typer.Option(..., "--weights"),
    mechid: int = typer.Option(0, "--mechid"),
    version_key: int = typer.Option(0, "--version-key"),
):
    """Commit timelock-encrypted weights (commit-reveal subnets)."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        CommitWeights(
            netuid=netuid,
            uids=_parse_int_list(uids),
            weights=_parse_float_list(weights),
            mechid=mechid,
            version_key=version_key,
        )
    )


@app.command("reveal")
@with_globals
def reveal_weights(
    ctx: typer.Context,
    netuid: int = typer.Option(..., "--netuid"),
    uids: str = typer.Option(..., "--uids"),
    weights: str = typer.Option(..., "--weights"),
    salt: str = typer.Option(..., "--salt", help="Comma-separated salt values used at commit time."),
    version_key: int = typer.Option(0, "--version-key"),
):
    """Reveal previously committed weights."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(
        RevealWeights(
            netuid=netuid,
            uids=_parse_int_list(uids),
            weights=_parse_float_list(weights),
            salt=_parse_int_list(salt),
            version_key=version_key,
        )
    )
