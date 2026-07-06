"""Block-pinned, read-only view of the chain: ``client.at(block)``.

Every read made through a snapshot resolves against the same block, which gives
two things: consistency (no torn reads across blocks) and speed (the block hash
is resolved once and served from the transport's cache afterwards, instead of
re-resolving the chain head on every call).

Write operations are rejected — a snapshot is a view, not a signer.
"""

from __future__ import annotations

import inspect
from typing import Any

from .result import BittensorError

_READ_NAMESPACES = ("balances", "subnets", "neurons", "staking")


class _PinnedNamespace:
    """Proxies a domain namespace, forcing ``block=`` on every read method."""

    def __init__(self, target: Any, block: int):
        self._target = target
        self._block = block

    def __getattr__(self, name: str):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr
        signature = inspect.signature(attr)
        if "block" not in signature.parameters:
            raise BittensorError(
                f"{type(self._target).__name__}.{name} is not a block-scoped read; "
                "snapshots are read-only. Use the client directly for writes."
            )

        async def pinned(*args, **kwargs):
            kwargs.setdefault("block", self._block)
            return await attr(*args, **kwargs)

        pinned.__name__ = name
        return pinned


class Snapshot:
    """All read namespaces, pinned to one block."""

    def __init__(self, client: Any, block: int):
        self.block = block
        for namespace in _READ_NAMESPACES:
            setattr(self, namespace, _PinnedNamespace(getattr(client, namespace), block))

    def __repr__(self) -> str:
        return f"Snapshot(block={self.block})"
