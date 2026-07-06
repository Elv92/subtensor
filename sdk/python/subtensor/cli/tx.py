"""The `subtensor tx` command group — generated from the intent registry.

Every registered intent becomes a subcommand whose options are derived from the
intent's dataclass fields (name, type, required-ness). There is no hand-written
command per operation: adding an intent to the SDK adds its CLI command for free,
and the two can't drift. The command body builds the intent from the parsed
options and runs it through the plan/confirm/execute choke point.

This is the CLI analogue of the tool manifest — both are projections of the same
single source of truth (the intents), one for humans, one for agents.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import MISSING, fields
from typing import Any, Optional

import typer

from ..intents import REGISTRY
from ..intents.base import Intent
from . import globals as g
from .context import address_cli_name, ctx_of, ss58_param_help

# Field annotation (as a string, under PEP 563) -> the Python type Typer should
# parse the option as. List/complex fields are taken as strings and parsed in the
# command body (see `_coerce`).
_SCALAR_TYPES = {"str": str, "int": int, "float": float, "bool": bool}


def _base_annotation(annotation: str) -> str:
    a = annotation.strip()
    if a.startswith("Optional[") and a.endswith("]"):
        a = a[len("Optional[") : -1].strip()
    if a.endswith("| None"):
        a = a[: -len("| None")].strip()
    return a


def _is_list(annotation: str) -> bool:
    return _base_annotation(annotation) in ("list",) or _base_annotation(annotation).startswith(
        "list["
    )


def _is_dict(annotation: str) -> bool:
    return _base_annotation(annotation) == "dict" or _base_annotation(annotation).startswith(
        "dict["
    )


def _option_type(annotation: str) -> type:
    """Typer parses scalars natively; everything else (lists, dicts) comes in as a string."""
    return _SCALAR_TYPES.get(_base_annotation(annotation), str)


def _coerce(field_annotation: str, value: Any) -> Any:
    """Parse a raw CLI value into what the intent field expects.

    List fields arrive as strings: JSON when they start with '[' (needed for
    lists of pairs like set_children), otherwise comma-separated scalars. Dict
    fields (e.g. a multisig inner call) arrive as a JSON string.
    """
    if value is None:
        return value
    if _is_dict(field_annotation):
        return json.loads(value) if isinstance(value, str) else value
    if not _is_list(field_annotation):
        return value
    text = str(value).strip()
    if text.startswith("["):
        return json.loads(text)
    inner = _base_annotation(field_annotation)
    cast = int if inner == "list[int]" else float if inner == "list[float]" else str
    return [cast(part.strip()) for part in text.split(",") if part.strip()]


def _make_command(intent_cls: type[Intent]):
    """Build a Typer command callback whose signature mirrors the intent's fields."""
    specs = list(fields(intent_cls))
    intent_names = {f.name for f in specs}
    # Global --proxy-for / --force-proxy-type wrap any intent in Proxy.proxy. Skip
    # them when the intent already owns a field with the same name (e.g.
    # ExecuteProxyAnnounced.force_proxy_type is the chain param, not the wrapper).
    global_proxy_type = "force_proxy_type" not in intent_names

    def command(ctx: typer.Context, **kwargs: Any) -> None:
        g.apply(ctx, kwargs)
        app_ctx = ctx_of(ctx)
        proxy_for = app_ctx.resolve_address("proxy_for", kwargs.pop("proxy_for", None))
        force_proxy_type = (
            kwargs.pop("force_proxy_type", None) if global_proxy_type else None
        )
        for f in specs:
            if f.name.endswith("_ss58"):
                kwargs[f.name] = app_ctx.resolve_address(f.name, kwargs.get(f.name))
        args = {
            f.name: _coerce(str(f.type), kwargs[f.name])
            for f in specs
            if kwargs.get(f.name) is not None
        }
        app_ctx.submit(
            intent_cls.from_args(args), proxy_for=proxy_for, force_proxy_type=force_proxy_type
        )

    # Synthesize the signature Typer introspects: ctx first, then one keyword
    # option per intent field, typed and defaulted from the dataclass.
    params = [
        inspect.Parameter("ctx", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=typer.Context)
    ]
    annotations: dict[str, Any] = {"ctx": typer.Context}
    for f in specs:
        # The canonical own-key params may be omitted: they fall back to the
        # configured wallet (see AppContext.resolve_address).
        wallet_defaulted = f.name in ("hotkey_ss58", "coldkey_ss58")
        required = f.default is MISSING and f.default_factory is MISSING and not wallet_defaulted
        cli_name = (
            address_cli_name(f.name) if f.name.endswith("_ss58") or "_ss58" in f.name else "--" + f.name.replace("_", "-")
        )
        help_text = ss58_param_help(f.name) if f.name.endswith("_ss58") else None
        default = ... if required else (None if wallet_defaulted else f.default)
        option = typer.Option(default, cli_name, help=help_text)
        opt_type = _option_type(str(f.type))
        annotations[f.name] = opt_type if required else Optional[opt_type]
        params.append(
            inspect.Parameter(
                f.name,
                inspect.Parameter.KEYWORD_ONLY,
                default=option,
                annotation=annotations[f.name],
            )
        )

    # Proxy signing mode, available on every mutation (see Executor.plan).
    proxy_params = [
        inspect.Parameter(
            "proxy_for",
            inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(
                None,
                "--proxy-for",
                help="Dispatch as this account (ss58 or local wallet name) via Proxy.proxy; "
                "your wallet key signs as its registered proxy.",
            ),
            annotation=Optional[str],
        ),
        inspect.Parameter(
            "force_proxy_type",
            inspect.Parameter.KEYWORD_ONLY,
            default=typer.Option(
                None,
                "--force-proxy-type",
                help="Require this exact proxy type to be used (with --proxy-for).",
            ),
            annotation=Optional[str],
        ),
    ]
    for p in proxy_params + g.parameters():
        if p.name in intent_names:
            continue
        annotations[p.name] = p.annotation
        params.append(p)
    command.__signature__ = inspect.Signature(params)
    command.__annotations__ = annotations
    command.__doc__ = (intent_cls.__doc__ or "").strip().split("\n")[0]
    return command


def build_tx_app() -> typer.Typer:
    """Assemble the `tx` group with one generated subcommand per registered intent."""
    app = typer.Typer(no_args_is_help=True, help="Submit transactions (generated from intents).")
    for op, intent_cls in sorted(REGISTRY.items()):
        app.command(op.replace("_", "-"))(_make_command(intent_cls))
    return app
