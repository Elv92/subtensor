"""`subtensor config`: persistent defaults for the global options.

Stored values seed the global options when neither a flag nor an env var is
given (see subtensor/config.py for the precedence rules).
"""

from __future__ import annotations

from typing import Optional

import typer

from ... import config as cfg
from ... import storage
from ..context import AppContext, ctx_of
from ..globals import with_globals

app = typer.Typer(no_args_is_help=True, help="Read and write persistent CLI config.")


@app.command("set")
@with_globals
def set_value(
    ctx: typer.Context,
    key: str = typer.Argument(..., help=f"One of: {', '.join(sorted(cfg.SETTABLE))}."),
    value: str = typer.Argument(..., help="Value to store."),
):
    """Set a persistent default, e.g. `subtensor config set network test`."""
    app_ctx: AppContext = ctx_of(ctx)
    try:
        stored = cfg.set_value(key, value)
    except ValueError as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)
    app_ctx.output.detail("set", {"key": key, "value": stored, "path": str(cfg.config_path())})


@app.command("get")
@with_globals
def get_value(
    ctx: typer.Context,
    key: Optional[str] = typer.Argument(None, help="Key to read; omit to show the whole config."),
):
    """Show one stored value, or the entire config."""
    app_ctx: AppContext = ctx_of(ctx)
    data = cfg.load()
    if key is None:
        app_ctx.output.detail(f"config ({cfg.config_path()})", data or {"(empty)": ""})
        return
    if key not in cfg.SETTABLE:
        app_ctx.output.error(f"unknown config key {key!r}; settable keys: {sorted(cfg.SETTABLE)}")
        raise typer.Exit(1)
    app_ctx.output.value(data.get(key))


@app.command("unset")
@with_globals
def unset_value(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Key to remove (reverts to env/default)."),
):
    """Remove a stored value."""
    app_ctx: AppContext = ctx_of(ctx)
    try:
        existed = cfg.unset_value(key)
    except ValueError as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)
    app_ctx.output.detail("unset", {"key": key, "existed": existed})


@app.command("clear")
@with_globals
def clear_config(ctx: typer.Context):
    """Clear all stored config values."""
    app_ctx: AppContext = ctx_of(ctx)
    data = cfg.load()
    for key in list(data):
        cfg.unset_value(key)
    app_ctx.output.detail("cleared config", {"path": str(cfg.config_path())})


@app.command("add-proxy")
@with_globals
def config_add_proxy(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name"),
    address: str = typer.Option(..., "--address", help="Pure or delegate proxy ss58."),
    spawner: str = typer.Option("", "--spawner"),
    proxy_type: str = typer.Option("Staking", "--proxy-type"),
    delay: int = typer.Option(0, "--delay"),
    note: str = typer.Option("", "--note"),
):
    """Add an entry to the local proxy address book."""
    app_ctx: AppContext = ctx_of(ctx)
    try:
        entry = cfg.add_proxy(
            {
                "name": name,
                "address": address,
                "spawner": spawner,
                "proxy_type": proxy_type,
                "delay": delay,
                "note": note,
            }
        )
    except ValueError as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)
    app_ctx.output.detail("added proxy", {"entry": entry, "path": str(cfg.proxies_path())})


@app.command("proxies")
@with_globals
def config_proxies(ctx: typer.Context):
    """List entries in the local proxy address book."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.output.detail(
        "proxy book", {"path": str(cfg.proxies_path()), "proxies": cfg.load_proxies()}
    )


@app.command("remove-proxy")
@with_globals
def config_remove_proxy(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Proxy book entry name."),
):
    """Remove a proxy book entry."""
    app_ctx: AppContext = ctx_of(ctx)
    existed = cfg.remove_proxy(name)
    app_ctx.output.detail("removed proxy", {"name": name, "existed": existed})


@app.command("update-proxy")
@with_globals
def config_update_proxy(
    ctx: typer.Context,
    name: str = typer.Argument(...),
    address: Optional[str] = typer.Option(None, "--address"),
    note: Optional[str] = typer.Option(None, "--note"),
):
    """Update a proxy book entry."""
    app_ctx: AppContext = ctx_of(ctx)
    updates = {k: v for k, v in {"address": address, "note": note}.items() if v is not None}
    updated = cfg.update_proxy(name, updates)
    if updated is None:
        app_ctx.output.error(f"proxy {name!r} not found")
        raise typer.Exit(1)
    app_ctx.output.detail("updated proxy", updated)


@app.command("clear-proxies")
@with_globals
def config_clear_proxies(ctx: typer.Context):
    """Clear the local proxy address book."""
    app_ctx: AppContext = ctx_of(ctx)
    count = cfg.clear_proxies()
    app_ctx.output.detail("cleared proxies", {"removed": count, "path": str(cfg.proxies_path())})


@app.command("path")
@with_globals
def show_path(ctx: typer.Context):
    """Print the config file path."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.output.value(str(cfg.config_path()))


@app.command("add-multisig")
@with_globals
def config_add_multisig(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Short name, e.g. finney-sudo."),
    threshold: int = typer.Option(..., "--threshold", min=1),
    signatories: Optional[str] = typer.Option(
        None,
        "--signatories",
        help="Full signer set: ss58, address-book names, or wallet names.",
    ),
    signatory: Optional[list[str]] = typer.Option(
        None, "--signatory", help="One signatory ref; repeat for each member."
    ),
    note: str = typer.Option("", "--note"),
):
    """Save a named multisig signer set for reuse with `subtensor call --multisig`."""
    app_ctx: AppContext = ctx_of(ctx)
    refs: list[str] = []
    if signatories:
        refs.extend(part.strip() for part in signatories.split(",") if part.strip())
    if signatory:
        refs.extend(signatory)
    refs = list(dict.fromkeys(refs))
    if not refs:
        app_ctx.output.error("pass --signatories or one or more --signatory")
        raise typer.Exit(1)
    try:
        addrs = [app_ctx.resolve_address("coldkey_ss58", ref) for ref in refs]
    except typer.Exit:
        raise
    addrs = list(dict.fromkeys(addrs))
    if threshold > len(addrs):
        app_ctx.output.error(f"threshold {threshold} exceeds {len(addrs)} signatories")
        raise typer.Exit(1)
    try:
        entry = cfg.add_multisig(
            {"name": name, "threshold": threshold, "signatories": addrs, "note": note}
        )
    except ValueError as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)
    app_ctx.output.detail(
        "saved multisig",
        {"entry": entry, "path": str(cfg.multisigs_path())},
    )


@app.command("multisigs")
@with_globals
def config_multisigs(ctx: typer.Context):
    """List saved multisig signer sets."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.output.detail(
        "multisig book",
        {"path": str(cfg.multisigs_path()), "multisigs": cfg.load_multisigs()},
    )


@app.command("remove-multisig")
@with_globals
def config_remove_multisig(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Saved multisig name."),
):
    """Remove a saved multisig signer set."""
    app_ctx: AppContext = ctx_of(ctx)
    existed = cfg.remove_multisig(name)
    app_ctx.output.detail("removed multisig", {"name": name, "existed": existed})


@app.command("show-multisig")
@with_globals
def config_show_multisig(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Saved multisig name."),
):
    """Derive the on-chain multisig address for a saved signer set."""
    app_ctx: AppContext = ctx_of(ctx)
    entry = cfg.get_multisig(name)
    if entry is None:
        app_ctx.output.error(f"multisig {name!r} not found")
        raise typer.Exit(1)

    signatories = [app_ctx.resolve_address("coldkey_ss58", ref) for ref in entry["signatories"]]
    signatories = list(dict.fromkeys(signatories))

    async def derive(client):
        ms = await client.multisig(signatories, entry["threshold"])
        sudo_key = await client.query(storage.Sudo.Key)
        return ms.address, sudo_key

    address, sudo_key = app_ctx.run(derive)
    app_ctx.output.detail(
        name,
        {
            "threshold": entry["threshold"],
            "signatories": signatories,
            "multisig_address": address,
            "chain_sudo_key": sudo_key,
            "matches_sudo": address == sudo_key,
        },
    )
