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
from ..extension.client import BridgeError
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
    signer_backend: Optional[str] = None
    signer_address: Optional[str] = None
    extension_source: Optional[str] = None
    extension_bridge_url: Optional[str] = None
    extension_browser: Optional[str] = None
    _extension_selection: Optional[object] = None
    _extension_bridge_ws_url: Optional[str] = None

    def reset_extension_session(self) -> None:
        self._extension_selection = None
        self._extension_bridge_ws_url = None

    def wallet(self):
        """Open the configured wallet handle (no key unlock; that happens on signing)."""
        return wallets.open_wallet(self.wallet_name, self.hotkey_name, self.wallet_path)

    def uses_extension_signer(self) -> bool:
        return (self.signer_backend or "").strip().lower() == "extension"

    async def extension_signer(self, *, pick_account: bool = False):
        """Connect to the bridge and return an extension-backed signer."""
        import sys

        from .. import config
        from ..extension import ensure_bridge, open_extension_signer, select_extension_account

        if pick_account or self._extension_selection is None:
            if not self.output.quiet:
                self.output.message(
                    "opening browser — authorize Talisman, Polkadot.js, or another "
                    "compatible extension for “Subtensor SDK”, then pick an account"
                )

            url = await ensure_bridge(
                bridge_url=self.extension_bridge_url,
                open_browser=not self.output.quiet and sys.stderr.isatty(),
                browser=self._extension_browser_choice(),
                on_waiting=lambda http_url, status: self.output.message(
                    "waiting for extension authorization in browser… "
                    f"({http_url})"
                ),
            )
            self._extension_bridge_ws_url = url

            def _remember(account) -> None:
                config.set_value("signer_address", account.address)

            explicit_address = self.signer_address
            self._extension_selection = await select_extension_account(
                url,
                address=explicit_address,
                source=self.extension_source,
                interactive=(
                    explicit_address is None
                    and sys.stdin.isatty()
                    and not self.output.json_mode
                ),
                default_address=None if explicit_address else config.get("signer_address"),
                on_picked=_remember,
            )
        elif self._extension_bridge_ws_url is None:
            self._extension_bridge_ws_url = await ensure_bridge(
                bridge_url=self.extension_bridge_url,
                open_browser=False,
                browser=self._extension_browser_choice(),
            )

        assert self._extension_bridge_ws_url is not None
        assert self._extension_selection is not None
        return await open_extension_signer(self._extension_bridge_ws_url, self._extension_selection)

    def _extension_browser_choice(self) -> Optional[str]:
        from .. import config

        return self.extension_browser or config.get("extension_browser")

    async def resolve_signing_wallet(self, role: str = "coldkey", *, pick_account: bool = False):
        """Return the configured signer for ``role`` (local wallet or extension)."""
        if self.uses_extension_signer():
            if role != "coldkey":
                raise ValueError("extension signing only supports coldkey intents")
            return await self.extension_signer(pick_account=pick_account)
        return self.signer(role)

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
        options = {"proxy_for": proxy_for, "proxy_type": force_proxy_type}
        summary = intent.summary() + (f" [as {proxy_for} via proxy]" if proxy_for else "")

        if self.uses_extension_signer():
            self.reset_extension_session()

        async def _plan(client):
            signer = await self.resolve_signing_wallet(intent.signer, pick_account=True)
            plan_target = signer if self.uses_extension_signer() else wallet
            try:
                return await client.plan(intent, plan_target, **options)
            finally:
                if self.uses_extension_signer() and hasattr(signer, "close"):
                    await signer.close()

        if self.dry_run:
            plan = self.run(_plan)
            self.output.plan(plan)
            if not plan.ok:
                raise typer.Exit(1)
            return

        if self.uses_extension_signer():
            async def _prepare(_client):
                signer = await self.extension_signer(pick_account=True)
                await signer.close()

            self.run(_prepare)

        self.confirm(f"{summary}?")

        async def _execute(client):
            signer = await self.resolve_signing_wallet(intent.signer)
            try:
                return await client.execute(
                    intent,
                    signer,
                    wait_for_finalization=False,
                    **options,
                )
            finally:
                if hasattr(signer, "close"):
                    await signer.close()

        result = self.run(_execute)
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
        except BridgeError as error:
            self.output.error(str(error))
            raise typer.Exit(1)
        except RuntimeError as error:
            if "different loop" in str(error).lower():
                self.output.error("extension bridge connection lost; retry the command")
                raise typer.Exit(1)
            raise
        except TypeError as error:
            self.output.error(str(error))
            raise typer.Exit(1)
        except (ConnectionError, TimeoutError, OSError) as error:
            self.output.error(f"could not reach {self.network}: {error}")
            raise typer.Exit(1)
        except KeyboardInterrupt:
            self.output.message("aborted.")
            raise typer.Exit(130)

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
