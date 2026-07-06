"""Synchronous facade over the async ``Client``.

There is exactly one implementation of the SDK (the async one). ``SyncClient``
runs a private event loop on a background thread and proxies every coroutine
method on the client's namespaces to it, so synchronous callers get a blocking
API without a second hand-written codebase.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Optional

from .client import Client
from .intents import Policy
from .settings import DEFAULT_NETWORK

_NAMESPACES = (
    "balances",
    "staking",
    "subnets",
    "neurons",
)


class _Loop:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def call(self, coro) -> Any:
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()

    def shutdown(self) -> None:
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


class _SyncNamespace:
    """Wraps an async namespace, turning each coroutine method into a blocking call."""

    def __init__(self, target: Any, loop: _Loop):
        self._target = target
        self._loop = loop

    def __getattr__(self, name: str):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs):
            return self._loop.call(attr(*args, **kwargs))

        wrapper.__name__ = name
        return wrapper


class SyncClient:
    def __init__(self, network: str = DEFAULT_NETWORK, *, policy: Optional[Policy] = None):
        self._loop = _Loop()
        self._client = Client(network, policy=policy)
        self.network = self._client.network
        self.endpoint = self._client.endpoint
        self._loop.call(self._client.connect())
        for ns in _NAMESPACES:
            setattr(self, ns, _SyncNamespace(getattr(self._client, ns), self._loop))

    @property
    def policy(self) -> Optional[Policy]:
        return self._client.policy

    @policy.setter
    def policy(self, value: Optional[Policy]) -> None:
        self._client.policy = value

    def block(self) -> int:
        return self._loop.call(self._client.block())

    def read(self, name: str, **params):
        return self._loop.call(self._client.read(name, **params))

    def reads(self) -> list[dict]:
        return self._client.reads()

    def submit_call(self, call, wallet, **kwargs):
        return self._loop.call(self._client.submit_call(call, wallet, **kwargs))

    def compose(self, call):
        return self._loop.call(self._client.compose(call))

    def multisig(self, signatories, threshold):
        multi = self._loop.call(self._client.multisig(signatories, threshold))
        return _SyncNamespace(multi, self._loop)

    def plan(self, intent, wallet, **kwargs):
        return self._loop.call(self._client.plan(intent, wallet, **kwargs))

    def execute(self, intent, wallet, **kwargs):
        return self._loop.call(self._client.execute(intent, wallet, **kwargs))

    def execute_tool(self, op, args, wallet, **kwargs):
        return self._loop.call(self._client.execute_tool(op, args, wallet, **kwargs))

    def submit_shielded(self, intent, wallet, **kwargs):
        return self._loop.call(self._client.submit_shielded(intent, wallet, **kwargs))

    def tools(self) -> list[dict]:
        return self._client.tools()

    def close(self) -> None:
        self._loop.call(self._client.close())
        self._loop.shutdown()

    def __enter__(self) -> "SyncClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"SyncClient(network={self.network!r}, endpoint={self.endpoint!r})"
