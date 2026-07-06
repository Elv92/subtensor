"""Proxy delegation: let a low-value key sign on behalf of the coldkey.

The security model: sign ``add_proxy`` once from the coldkey (granting a scoped
``proxy_type`` to a delegate key), then keep the coldkey offline. The delegate
executes any intent with ``proxy_for=<coldkey ss58>`` (see ``Executor``), which
wraps the call in ``Proxy.proxy`` so it dispatches with the coldkey's origin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from .base import Intent
from .registry import build as build_intent, register

# Variants of the runtime's ProxyType enum (subtensor/common/src/lib.rs).
PROXY_TYPES = (
    "Any",
    "Owner",
    "NonCritical",
    "NonTransfer",
    "Senate",
    "NonFungible",
    "Triumvirate",
    "Governance",
    "Staking",
    "Registration",
    "Transfer",
    "SmallTransfer",
    "RootWeights",
    "ChildKeys",
    "SudoUncheckedSetCode",
    "SwapHotkey",
    "SubnetLeaseBeneficiary",
    "RootClaim",
)


def check_proxy_type(proxy_type: str) -> str:
    if proxy_type not in PROXY_TYPES:
        raise ValueError(
            f"unknown proxy type {proxy_type!r}; expected one of: {', '.join(PROXY_TYPES)}"
        )
    return proxy_type


@register
@dataclass
class AddProxy(Intent):
    """Authorize a delegate key to sign calls on this account's behalf.

    ``proxy_type`` bounds what the delegate may do (e.g. ``Staking``); prefer the
    narrowest type that covers your use. ``delay`` (in blocks) forces the delegate
    to announce each call that long in advance — 0 means immediate.
    """

    op = "add_proxy"
    signer = "coldkey"
    wraps = (("Proxy", "add_proxy"),)

    delegate_ss58: str
    proxy_type: str = "Staking"
    delay: int = 0

    def __post_init__(self):
        check_proxy_type(self.proxy_type)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Proxy.add_proxy(
                delegate=self.delegate_ss58, proxy_type=self.proxy_type, delay=self.delay
            )
        )

    def summary(self) -> str:
        return f"add {self.proxy_type} proxy {self.delegate_ss58} (delay {self.delay})"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        out = ["reserves a proxy deposit from the signer (returned on removal)"]
        if self.proxy_type == "Any":
            out.append(
                "an Any proxy can do everything this account can, including transfers; "
                "prefer a narrower proxy type"
            )
        return out


@register
@dataclass
class RemoveProxy(Intent):
    """Revoke one proxy delegation (must match type and delay exactly)."""

    op = "remove_proxy"
    signer = "coldkey"
    wraps = (("Proxy", "remove_proxy"),)

    delegate_ss58: str
    proxy_type: str = "Staking"
    delay: int = 0

    def __post_init__(self):
        check_proxy_type(self.proxy_type)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Proxy.remove_proxy(
                delegate=self.delegate_ss58, proxy_type=self.proxy_type, delay=self.delay
            )
        )

    def summary(self) -> str:
        return f"remove {self.proxy_type} proxy {self.delegate_ss58} (delay {self.delay})"


@register
@dataclass
class RemoveProxies(Intent):
    """Revoke every proxy delegation for the signing account."""

    op = "remove_proxies"
    signer = "coldkey"
    wraps = (("Proxy", "remove_proxies"),)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(calls.Proxy.remove_proxies())

    def summary(self) -> str:
        return "remove ALL proxies for the signer"

    async def warnings(self, substrate, signer_address: str) -> list[str]:
        return ["revokes every delegate at once; pure-proxy accounts would become inaccessible"]


@register
@dataclass
class CreatePureProxy(Intent):
    """Create a pure proxy account (anonymous proxy derived from spawner + index)."""

    op = "create_pure_proxy"
    signer = "coldkey"
    wraps = (("Proxy", "create_pure"),)

    proxy_type: str = "Staking"
    delay: int = 0
    index: int = 0

    def __post_init__(self):
        check_proxy_type(self.proxy_type)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Proxy.create_pure(
                proxy_type=self.proxy_type, delay=self.delay, index=self.index
            )
        )

    def summary(self) -> str:
        return f"create pure {self.proxy_type} proxy (index {self.index}, delay {self.delay})"


@register
@dataclass
class KillPureProxy(Intent):
    """Close a pure proxy account and return its reserved deposit."""

    op = "kill_pure_proxy"
    signer = "coldkey"
    wraps = (("Proxy", "kill_pure"),)

    spawner_ss58: str
    proxy_type: str = "Staking"
    index: int = 0
    height: int = 0
    ext_index: int = 0

    def __post_init__(self):
        check_proxy_type(self.proxy_type)

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.Proxy.kill_pure(
                spawner=self.spawner_ss58,
                proxy_type=self.proxy_type,
                index=self.index,
                height=self.height,
                ext_index=self.ext_index,
            )
        )

    def summary(self) -> str:
        return f"kill pure proxy index {self.index} for {self.spawner_ss58}"


@register
@dataclass
class ExecuteProxyAnnounced(Intent):
    """Execute a previously announced proxy call."""

    op = "execute_proxy_announced"
    signer = "coldkey"
    wraps = (("Proxy", "proxy_announced"),)

    delegate_ss58: str
    real_ss58: str
    inner_op: str
    inner_args: dict
    force_proxy_type: Optional[str] = None

    async def build(self, substrate, wallet: Any):
        inner = await build_intent(self.inner_op, self.inner_args).build(substrate, wallet)
        inner_call = inner.call if hasattr(inner, "call") else inner
        return await substrate.compose(
            calls.Proxy.proxy_announced(
                delegate=self.delegate_ss58,
                real=self.real_ss58,
                force_proxy_type=self.force_proxy_type,
                call=inner_call,
            )
        )

    def summary(self) -> str:
        return f"execute announced {self.inner_op} as {self.real_ss58} via {self.delegate_ss58}"
