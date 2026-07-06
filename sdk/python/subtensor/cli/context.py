"""Shared per-invocation state and the single place chain work is executed.

The top-level callback builds one ``AppContext`` and stashes it on the Typer
context. Every command pulls global options (network, wallet, output mode) from
it instead of redeclaring them, and runs all its chain work through
``AppContext.run`` so connection lifecycle and error handling live in one place.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, TypeVar

import typer
from bittensor_wallet.utils import is_valid_ss58_address

from .. import config as cfg
from .. import wallets
from ..client import Client
from ..result import BittensorError
from .output import Output

T = TypeVar("T")


def address_cli_name(param: str) -> str:
    """CLI flag for a param resolved by ``resolve_address`` (drops the ``_ss58`` suffix)."""
    if param.endswith("_ss58"):
        base = param[: -len("_ss58")]
    else:
        base = param.replace("_ss58", "")
    return "--" + base.replace("_", "-")


def ss58_param_help(param: str) -> str:
    """Help text for an address-typed CLI option (see AppContext.resolve_address)."""
    book = "address-book name, "
    if "hotkey" in param:
        text = f"ss58 address, {book}or a local hotkey name (HOTKEY or WALLET/HOTKEY)."
        if param == "hotkey_ss58":
            text += " Defaults to your wallet's hotkey."
    else:
        text = f"ss58 address, {book}or a local wallet name (uses its coldkey)."
        if param == "coldkey_ss58":
            text += " Defaults to your wallet's coldkey."
    return text


@dataclass
class AppContext:
    network: str
    wallet_name: str
    hotkey_name: str
    wallet_path: str
    assume_yes: bool
    dry_run: bool
    output: Output
    wallet_password_file: Optional[str] = None
    macos_password: bool = False
    keychain_password: bool = False

    def wallet(self):
        """Open the configured wallet handle (no key unlock; that happens on signing)."""
        return wallets.open_wallet(self.wallet_name, self.hotkey_name, self.wallet_path)

    def signer(self, role: str = "coldkey"):
        """Signing handle with configured password sources (macOS dialog, Keychain, file)."""
        from ..signing import WalletSigner

        wallet = self.wallet()
        if not (self.macos_password or self.keychain_password or self.wallet_password_file):
            return wallet
        return WalletSigner(
            wallet,
            role,
            password_file=self.wallet_password_file,
            macos_prompt=self.macos_password,
            keychain=self.keychain_password,
        )

    def resolve_address(self, param: str, value: Optional[str]) -> Optional[str]:
        """Resolve an address-typed CLI value (any ``*_ss58`` param) to an ss58 address.

        Four accepted forms:
        - a raw ss58 address: used as-is;
        - an address-book name (``subtensor addresses NAME SS58``);
        - a local key reference: hotkey params take ``HOTKEY`` (in the configured
          wallet) or ``WALLET/HOTKEY``; coldkey params take a ``WALLET`` name
          (resolved to its coldkey);
        - omitted: only the canonical ``hotkey_ss58`` / ``coldkey_ss58`` params
          fall back to the configured wallet's own key. Destination-style params
          (``--dest``, ``--destination-hotkey``, ...) never default.
        """
        if value is not None and is_valid_ss58_address(value):
            return value
        if value is not None:
            booked = cfg.get_address(value)
            if booked:
                return booked
        try:
            if value is None:
                if param == "hotkey_ss58":
                    return self.wallet().hotkey.ss58_address
                if param == "coldkey_ss58":
                    return self.wallet().coldkeypub.ss58_address
                return None
            if "hotkey" in param:
                wallet_name, _, hotkey = value.rpartition("/")
                handle = wallets.open_wallet(
                    wallet_name or self.wallet_name, hotkey, self.wallet_path
                )
                return handle.hotkey.ss58_address
            return wallets.open_wallet(name=value, path=self.wallet_path).coldkeypub.ss58_address
        except Exception as error:
            shown = value if value is not None else f"{self.wallet_name}/{self.hotkey_name}"
            self.output.error(f"cannot resolve {address_cli_name(param)} {shown!r}: {error}")
            raise typer.Exit(1)

    def resolve_signatory_list(self, raw: str) -> list[str]:
        """Resolve comma-separated signatory refs (ss58, address-book name, wallet)."""
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            raise ValueError("need at least one signatory")
        resolved: list[str] = []
        for part in parts:
            address = self.resolve_address("coldkey_ss58", part)
            if not address:
                raise ValueError(f"cannot resolve {part!r}")
            resolved.append(address)
        return list(dict.fromkeys(resolved))

    def submit(
        self,
        intent,
        *,
        proxy_for: Optional[str] = None,
        force_proxy_type: Optional[str] = None,
    ) -> None:
        """Run a mutation with a uniform dry-run / confirm / execute / render flow.

        ``--dry-run`` shows the plan (fee, effects, warnings, policy) and stops.
        Otherwise the intent's own summary is the confirmation prompt; the intent
        is then executed and its result rendered. The prompt/summary is never
        hand-written per command — it comes from the intent.

        ``proxy_for`` dispatches the call as that account via ``Proxy.proxy``,
        signed by the local wallet key (which must be its registered proxy).
        """
        wallet = self.wallet()
        signer = self.signer(intent.signer)
        options = {"proxy_for": proxy_for, "proxy_type": force_proxy_type}
        summary = intent.summary() + (f" [as {proxy_for} via proxy]" if proxy_for else "")
        if self.dry_run:
            plan = self.run(lambda client: client.plan(intent, wallet, **options))
            self.output.plan(plan)
            if not plan.ok:
                raise typer.Exit(1)
            return
        self.confirm(f"{summary}?")
        result = self.run(
            lambda client: client.execute(
                intent,
                signer,
                wait_for_finalization=False,
                **options,
            )
        )
        if not self.output.result(result, summary):
            raise typer.Exit(1)

    def run(self, work: Callable[[Client], Awaitable[T]]) -> T:
        """Open a client, run ``work``, and translate SDK/connection errors into
        clean messages with a non-zero exit code (never a traceback)."""

        async def _main() -> T:
            async with Client(self.network) as client:
                return await work(client)

        try:
            return asyncio.run(_main())
        except (BittensorError, ValueError) as error:
            self.output.error(str(error))
            raise typer.Exit(1)
        except (ConnectionError, TimeoutError, OSError) as error:
            self.output.error(f"could not reach {self.network}: {error}")
            raise typer.Exit(1)

    def confirm(self, prompt: str) -> None:
        """Gate a state-changing action. ``--yes`` skips it; a non-interactive
        session without ``--yes`` is refused rather than left hanging on a prompt."""
        if self.assume_yes:
            return
        if self.output.json_mode or not sys.stdin.isatty():
            self.output.error("refusing to submit without confirmation; pass --yes")
            raise typer.Exit(1)
        if not typer.confirm(prompt):
            self.output.message("aborted.")
            raise typer.Exit(1)


def ctx_of(ctx: typer.Context) -> AppContext:
    """Fetch the AppContext built by the root callback."""
    return ctx.obj
