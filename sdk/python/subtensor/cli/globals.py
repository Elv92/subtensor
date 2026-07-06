"""Global options, available on every command for discoverability.

The root callback sets defaults (from flags/env), so ``subtensor -n test <cmd>``
still works. In addition, every command carries the same options as *overrides*
(default None/False, no env) so they also show in that command's ``--help`` and
can be passed after the subcommand: ``subtensor <cmd> -n test``. When a command's
override is set, it wins over the root default.

Both the generated commands (tx/query) and the hand-written ones share this one
definition, so the global surface can't drift between them.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Optional

import typer

# (param_name, annotation, typer.Option) — override form: None/False defaults, no env.
_SPECS = [
    (
        "network",
        Optional[str],
        typer.Option(
            None, "--network", "-n", help="Network name (finney/test/local) or ws:// endpoint."
        ),
    ),
    ("wallet", Optional[str], typer.Option(None, "--wallet", "-w", help="Coldkey wallet name.")),
    (
        "wallet_hotkey",
        Optional[str],
        typer.Option(None, "--wallet-hotkey", "-H", help="Hotkey name within the wallet."),
    ),
    ("wallet_path", Optional[str], typer.Option(None, "--wallet-path", help="Wallet directory.")),
    ("json_output", bool, typer.Option(False, "--json", help="Machine-readable JSON output.")),
    ("assume_yes", bool, typer.Option(False, "--yes", "-y", help="Skip confirmation prompts.")),
    (
        "dry_run",
        bool,
        typer.Option(False, "--dry-run", help="Preview mutations without submitting."),
    ),
    ("quiet", bool, typer.Option(False, "--quiet", "-q", help="Suppress informational output.")),
    (
        "wallet_password_file",
        Optional[str],
        typer.Option(
            None,
            "--wallet-password-file",
            envvar="BT_WALLET_PASSWORD_FILE",
            help="File containing the coldkey password (one line).",
        ),
    ),
    (
        "macos_password",
        bool,
        typer.Option(
            False,
            "--macos-password",
            help="Unlock encrypted coldkeys via a native macOS password dialog.",
        ),
    ),
    (
        "keychain_password",
        bool,
        typer.Option(
            False,
            "--keychain-password",
            help="Unlock encrypted coldkeys from the macOS Keychain (see wallet keychain save).",
        ),
    ),
]


def parameters() -> list[inspect.Parameter]:
    """The global options as keyword-only signature parameters (for generated commands)."""
    return [
        inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=option, annotation=ann)
        for name, ann, option in _SPECS
    ]


def apply(ctx: typer.Context, kwargs: dict[str, Any]) -> None:
    """Pop the global options out of ``kwargs`` and override the AppContext where set."""
    obj = ctx.obj
    if v := kwargs.pop("network", None):
        obj.network = v
    if v := kwargs.pop("wallet", None):
        obj.wallet_name = v
    if v := kwargs.pop("wallet_hotkey", None):
        obj.hotkey_name = v
    if v := kwargs.pop("wallet_path", None):
        obj.wallet_path = v
    if kwargs.pop("json_output", False):
        obj.output.json_mode = True
    if kwargs.pop("assume_yes", False):
        obj.assume_yes = True
    if kwargs.pop("dry_run", False):
        obj.dry_run = True
    if kwargs.pop("quiet", False):
        obj.output.quiet = True
    if v := kwargs.pop("wallet_password_file", None):
        obj.wallet_password_file = v
    if kwargs.pop("macos_password", False):
        obj.macos_password = True
    if kwargs.pop("keychain_password", False):
        obj.keychain_password = True


def with_globals(fn: Callable) -> Callable:
    """Decorator: add the global options to a hand-written command and apply them.

    The wrapped command keeps its own options; the globals are appended and merged
    into the AppContext before the command body runs.
    """
    original = inspect.signature(fn)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        ctx = kwargs.get("ctx") or (args[0] if args else None)
        apply(ctx, kwargs)
        return fn(*args, **kwargs)

    wrapper.__signature__ = original.replace(
        parameters=list(original.parameters.values()) + parameters()
    )
    annotations = dict(getattr(fn, "__annotations__", {}))
    for name, ann, _ in _SPECS:
        annotations[name] = ann
    wrapper.__annotations__ = annotations
    return wrapper
