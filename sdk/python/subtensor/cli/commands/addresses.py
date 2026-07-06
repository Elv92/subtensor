"""`subtensor addresses`: local ss58 address book for named contacts."""

from __future__ import annotations

from pathlib import Path

import typer
from bittensor_wallet.utils import is_valid_ss58_address

from ... import config as cfg
from ..context import AppContext, ctx_of
from ..globals import with_globals

app = typer.Typer(
    no_args_is_help=True,
    help="Save and reuse named ss58 addresses (for multisig signers, destinations, etc.).",
)


def _display_path(path: Path) -> str:
    text = str(path.expanduser())
    home = str(Path.home())
    if text.startswith(home):
        return "~" + text[len(home) :]
    return text


def _save(app_ctx: AppContext, name: str, ss58: str, note: str) -> None:
    if not is_valid_ss58_address(ss58):
        app_ctx.output.error(f"invalid ss58 address {ss58!r}")
        raise typer.Exit(1)
    try:
        entry = cfg.add_address({"name": name, "address": ss58, "note": note})
    except ValueError as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)
    app_ctx.output.detail("saved address", {"entry": entry, "path": str(cfg.addresses_path())})


@app.command("add")
@with_globals
def add_address(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Contact name to save."),
    ss58: str = typer.Argument(..., help="ss58 address for that name."),
    note: str = typer.Option("", "--note", help="Optional note stored with the entry."),
):
    """Save a named address: `subtensor addresses add triumph-a 5FHne...`."""
    _save(ctx_of(ctx), name, ss58, note)


@app.command()
@with_globals
def save(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Contact name to save."),
    ss58: str = typer.Argument(..., help="ss58 address for that name."),
    note: str = typer.Option("", "--note", help="Optional note stored with the entry."),
):
    """Alias for `add`: `subtensor addresses save triumph-a 5FHne...`."""
    _save(ctx_of(ctx), name, ss58, note)


@app.command("list")
@with_globals
def list_addresses(ctx: typer.Context):
    """List saved address-book entries."""
    app_ctx: AppContext = ctx_of(ctx)
    entries = cfg.load_addresses()
    path = cfg.addresses_path()
    if app_ctx.output.json_mode:
        app_ctx.output.value({"path": str(path), "addresses": entries})
        return
    if not entries:
        app_ctx.output.detail("address book", {"path": _display_path(path), "entries": 0})
        return
    rows = [
        [entry.get("name", ""), entry.get("address", ""), entry.get("note", "") or "—"]
        for entry in entries
    ]
    app_ctx.output.table("address book", ["name", "address", "note"], rows, entries)
    app_ctx.output.message(
        f"  {_display_path(path)}  ·  {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"
    )


@app.command("show")
@with_globals
def show_address(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Saved contact name."),
):
    """Show one saved address."""
    app_ctx: AppContext = ctx_of(ctx)
    entry = next((e for e in cfg.load_addresses() if e.get("name") == name), None)
    if entry is None:
        app_ctx.output.error(f"address {name!r} not found")
        raise typer.Exit(1)
    app_ctx.output.detail(name, entry)


@app.command("remove")
@with_globals
def remove_address(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Saved contact name."),
):
    """Remove a saved address."""
    app_ctx: AppContext = ctx_of(ctx)
    existed = cfg.remove_address(name)
    app_ctx.output.detail("removed address", {"name": name, "existed": existed})
