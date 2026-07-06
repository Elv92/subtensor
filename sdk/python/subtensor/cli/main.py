"""subtensor: the command line for the Bittensor chain.

Global options (network, wallet identity, output mode) are declared on the root
callback (with env defaults) and *also* on every subcommand as overrides, so they
show up in each command's --help and can be passed either before or after the
subcommand (see cli/globals.py). Reads need no wallet; writes confirm before
submitting unless ``--yes`` is given.
"""

from __future__ import annotations

import json
from typing import Optional

import typer

from .. import __version__, wallets
from ..config import get as config_default
from ..intents import list_tools
from ..settings import DEFAULT_NETWORK
from .call import call as call_command
from .commands import (
    addresses,
    axon,
    balance,
    config,
    crowd,
    deriv,
    extension,
    liquidity,
    lock,
    proxy,
    stake,
    subnets,
    sudo,
    utils,
    view,
    wallet,
    weights,
)
from .context import AppContext
from .output import Output
from .query import build_query_app
from .tx import build_tx_app

app = typer.Typer(
    no_args_is_help=True,
    add_completion=True,
    help="subtensor - a lean command line for the Bittensor chain.",
)

# Hand-written command groups
app.add_typer(wallet.app, name="wallet")
app.add_typer(extension.app, name="extension")
app.add_typer(balance.app, name="balance")
app.add_typer(stake.app, name="stake")
app.add_typer(subnets.app, name="subnets")
app.add_typer(config.app, name="config")
app.add_typer(addresses.app, name="addresses")
app.add_typer(lock.app, name="lock")
app.add_typer(liquidity.app, name="liquidity")
app.add_typer(deriv.app, name="deriv")
app.add_typer(weights.app, name="weights")
app.add_typer(sudo.app, name="sudo")
app.add_typer(proxy.app, name="proxy")
app.add_typer(crowd.app, name="crowd")
app.add_typer(axon.app, name="axon")
app.add_typer(view.app, name="view")
app.add_typer(utils.app, name="utils")

# Generated from registries
app.add_typer(build_query_app(), name="query")
app.add_typer(build_tx_app(), name="tx")

# Escape hatches / tooling
app.command("call")(call_command)


def _version(show: bool) -> None:
    if show:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    network: str = typer.Option(
        config_default("network", DEFAULT_NETWORK),
        "--network",
        "-n",
        envvar="BT_NETWORK",
        help="Network name (finney/test/local) or a ws:// endpoint.",
    ),
    wallet_name: str = typer.Option(
        config_default("wallet", "default"),
        "--wallet",
        "-w",
        envvar="BT_WALLET",
        help="Coldkey wallet name.",
    ),
    hotkey_name: str = typer.Option(
        config_default("wallet_hotkey", "default"),
        "--wallet-hotkey",
        "-H",
        envvar="BT_WALLET_HOTKEY",
        help="Hotkey name within the wallet.",
    ),
    wallet_path: str = typer.Option(
        config_default("wallet_path", wallets.DEFAULT_WALLET_PATH),
        "--wallet-path",
        envvar="BT_WALLET_PATH",
    ),
    json_output: bool = typer.Option(
        config_default("json", False), "--json", help="Emit machine-readable JSON."
    ),
    assume_yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompts."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview mutations (fee, effects) without submitting."
    ),
    quiet: bool = typer.Option(
        config_default("quiet", False), "--quiet", "-q", help="Suppress informational output."
    ),
    signer_backend: Optional[str] = typer.Option(
        None,
        "--signer",
        help="Signing backend: wallet (default) or extension.",
    ),
    signer_address: Optional[str] = typer.Option(
        config_default("signer_address"),
        "--signer-address",
        envvar="BT_SIGNER_ADDRESS",
        help="Extension account ss58 address (optional; prompts when omitted).",
    ),
    extension_source: Optional[str] = typer.Option(
        None,
        "--extension-source",
        help="Filter extension accounts by source (e.g. talisman, polkadot-js).",
    ),
    extension_browser: Optional[str] = typer.Option(
        config_default("extension_browser"),
        "--extension-browser",
        envvar="BT_EXTENSION_BROWSER",
        help="Browser for the bridge page: firefox, chrome, or an app name.",
    ),
    extension_bridge_url: Optional[str] = typer.Option(
        None,
        "--extension-bridge",
        envvar="BT_EXTENSION_BRIDGE",
        help="Extension bridge WebSocket URL.",
    ),
    _v: Optional[bool] = typer.Option(
        None, "--version", callback=_version, is_eager=True, help="Show version and exit."
    ),
):
    ctx.obj = AppContext(
        network=network,
        wallet_name=wallet_name,
        hotkey_name=hotkey_name,
        wallet_path=wallet_path,
        assume_yes=assume_yes,
        dry_run=dry_run,
        output=Output(json_mode=json_output, quiet=quiet),
        signer_backend=signer_backend,
        signer_address=signer_address,
        extension_source=extension_source,
        extension_browser=extension_browser,
        extension_bridge_url=extension_bridge_url,
    )


@app.command("tools")
def tools():
    """Print the machine-readable operation catalog (JSON) for agents."""
    typer.echo(json.dumps(list_tools(), indent=2))


def main() -> None:
    import sys

    from bittensor_wallet.utils import is_valid_ss58_address

    argv = sys.argv[1:]
    if (
        len(argv) >= 3
        and argv[0] == "addresses"
        and argv[1] not in ("add", "save", "list", "show", "remove")
        and not argv[1].startswith("-")
        and not argv[2].startswith("-")
        and is_valid_ss58_address(argv[2])
    ):
        sys.argv.insert(2, "add")
    app()


if __name__ == "__main__":
    main()
