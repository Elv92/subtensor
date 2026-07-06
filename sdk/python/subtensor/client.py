"""The async entry point: ``Client``.

A ``Client`` owns one chain connection and has two verbs, each a projection of
the chain's own metadata:

- **Read state.** Generic ``query`` / ``query_map`` / ``runtime`` / ``constant``
  over the generated descriptors (``subtensor.storage`` / ``runtime_api`` /
  ``constants``), plus a few typed conveniences (``balances``, ``subnets``,
  ``neurons``, ``staking``) that decode or aggregate.
- **Submit an intent.** ``plan`` / ``execute`` / ``execute_tool`` — mutations as
  serializable data, previewed with fee + effects, gated by an optional
  :class:`Policy`.

Open with ``async with`` or ``connect()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional

from . import reads as read_registry
from ._substrate import Substrate
from .balances import Balances
from .executor import Executor
from .intents import Intent, Plan, Policy
from .multisig import Multisig
from .neurons import Neurons
from .result import ExtrinsicResult
from .settings import DEFAULT_NETWORK, resolve_endpoint
from .snapshot import Snapshot
from .staking import Staking
from .subnets import Subnets

# A generated descriptor is a (container, name) pair (see subtensor/_generated).
Descriptor = tuple


@dataclass
class BlockHeader:
    """A new block seen on a subscription (``client.blocks()``)."""

    number: int
    parent_hash: Optional[str]
    raw: dict = field(repr=False)


class Client:
    def __init__(self, network: str = DEFAULT_NETWORK, *, policy: Optional[Policy] = None):
        """Create a client for a network name (``finney``/``test``/``local``) or a
        raw ``ws://`` / ``wss://`` endpoint. An optional ``policy`` guards every
        mutation. The connection opens on ``connect()``.
        """
        self.network, self.endpoint = resolve_endpoint(network)
        self._substrate = Substrate(self.endpoint)
        self._executor = Executor(self._substrate, policy=policy)

        # Typed read conveniences (decode/aggregate). Anything else is reachable
        # via the generic query/runtime accessors below.
        self.balances = Balances(self._substrate)
        self.subnets = Subnets(self._substrate)
        self.neurons = Neurons(self._substrate)
        self.staking = Staking(self._substrate)

    # Reads: generic accessors over generated descriptors ---------------------

    async def _block_hash(self, block: Optional[int]) -> Optional[str]:
        return await self._substrate.block_hash(block) if block is not None else None

    async def query(
        self, item: Descriptor, params: Optional[list] = None, *, block: Optional[int] = None
    ) -> Any:
        """Read a storage item, e.g. ``client.query(storage.SubtensorModule.Tempo, [netuid])``."""
        return await self._substrate.query(
            item[0], item[1], params, block_hash=await self._block_hash(block)
        )

    async def query_map(
        self, item: Descriptor, params: Optional[list] = None, *, block: Optional[int] = None
    ) -> list[tuple[Any, Any]]:
        """Read a whole storage map, e.g. ``client.query_map(storage.SubtensorModule.Tempo)``."""
        return await self._substrate.query_map(
            item[0], item[1], params, block_hash=await self._block_hash(block)
        )

    async def runtime(
        self, method: Descriptor, params: list, *, block: Optional[int] = None
    ) -> Any:
        """Call a runtime API, e.g. ``client.runtime(runtime_api.NeuronInfoRuntimeApi.get_neurons_lite, [netuid])``."""
        return await self._substrate.runtime_call(
            method[0], method[1], params, block_hash=await self._block_hash(block)
        )

    async def constant(self, item: Descriptor) -> Any:
        """Read a pallet constant, e.g. ``client.constant(constants.Balances.ExistentialDeposit)``."""
        return await self._substrate.constant(item[0], item[1])

    async def read(self, name: str, **params: Any) -> Any:
        """Run a named typed read (see ``reads()`` for the catalog).

        e.g. ``await client.read("subnet_hyperparameters", netuid=1)``.
        """
        try:
            spec = read_registry.REGISTRY[name]
        except KeyError:
            raise ValueError(
                f"Unknown read {name!r}. Known reads: {sorted(read_registry.REGISTRY)}"
            ) from None
        return await spec.fetch(self, **params)

    def reads(self) -> list[dict]:
        """Machine-readable catalog of every typed read (for agents)."""
        return read_registry.list_reads()

    async def blocks(self, *, finalized: bool = False) -> AsyncIterator[BlockHeader]:
        """Stream new block headers as they are produced (or finalized).

        e.g. ``async for header in client.blocks(): ...`` — break out of the loop
        to cancel the underlying subscription.
        """
        async for block in self._substrate.blocks(finalized=finalized):
            header = block.get("header") or {}
            yield BlockHeader(
                number=int(header["number"]),
                parent_hash=header.get("parentHash"),
                raw=header,
            )

    # Intent layer -----------------------------------------------------------

    async def plan(self, intent: Intent, wallet: Any, **kwargs) -> Plan:
        """Preview an intent (fee, effects, warnings, policy) without submitting.

        This is the dry run: to see what a mutation would do, ``plan`` it. Accepts
        the same ``policy`` / ``proxy_for`` / ``proxy_type`` options as ``execute``.
        """
        return await self._executor.plan(intent, wallet, **kwargs)

    async def execute(self, intent: Intent, wallet: Any, **kwargs) -> ExtrinsicResult:
        """Sign and submit an intent through the policy-gated choke point.

        Raises :class:`PolicyError` if the intent violates the active policy.
        """
        return await self._executor.execute(intent, wallet, **kwargs)

    async def execute_tool(self, op: str, args: dict, wallet: Any, **kwargs) -> ExtrinsicResult:
        """Build an intent by name from a dict of args and execute it."""
        return await self._executor.execute_tool(op, args, wallet, **kwargs)

    async def submit_shielded(self, intent: Intent, wallet: Any, **kwargs) -> ExtrinsicResult:
        """Submit an intent MEV-shielded (encrypted until block-author execution).

        Same policy gating as :meth:`execute`; see ``Executor.submit_shielded``.
        """
        return await self._executor.submit_shielded(intent, wallet, **kwargs)

    async def submit_call(self, call, wallet: Any, **kwargs) -> ExtrinsicResult:
        """Escape hatch: submit any generated raw call (``subtensor.calls``) directly.

        No intent, no preview — an active :class:`Policy` refuses this unless it
        sets ``allow_raw_calls=True``. Pass ``signer="hotkey"`` for hotkey-signed
        extrinsics.
        """
        return await self._executor.submit_call(call, wallet, **kwargs)

    async def compose(self, call):
        """Compose a generated call into a chain-ready call object.

        Needed to nest one call inside another — the inner call of ``Sudo.sudo``,
        ``Utility.batch``, or ``Proxy.proxy`` must be composed before it becomes a
        parameter, e.g.::

            inner = await client.compose(sub.calls.System.set_code(code=wasm_hex))
            await client.submit_call(sub.calls.Sudo.sudo(call=inner), sudo_wallet)
        """
        return await self._substrate.compose(call)

    async def multisig(self, signatories: list[str], threshold: int) -> Multisig:
        """A handle to the M-of-N multisig account for a signer set.

        The address is derived deterministically from the signatory *set* and
        ``threshold`` against the connected runtime. Have each signatory call
        ``approve(call, wallet)`` on the returned object; the one that reaches the
        threshold executes the call.
        """
        account = self._substrate.multisig_account(signatories, threshold)
        return Multisig(
            signatories=list(signatories),
            threshold=threshold,
            address=account.ss58_address,
            _client=self,
            _account=account,
        )

    def tools(self) -> list[dict]:
        """Machine-readable catalog of every executable operation (for agents)."""
        return self._executor.tools()

    @property
    def policy(self) -> Optional[Policy]:
        return self._executor.policy

    @policy.setter
    def policy(self, value: Optional[Policy]) -> None:
        self._executor.policy = value

    # Lifecycle --------------------------------------------------------------

    async def connect(self) -> "Client":
        await self._substrate.connect()
        return self

    async def close(self) -> None:
        await self._substrate.close()

    async def block(self) -> int:
        """Current chain block number."""
        return await self._substrate.block_number()

    async def at(self, block: Optional[int] = None) -> Snapshot:
        """A read-only view pinned to ``block`` (defaults to the current head).

        All reads through the snapshot hit the same block: consistent values,
        and the block hash resolves once instead of per call.
        """
        if block is None:
            block = await self._substrate.block_number()
        return Snapshot(self, block)

    async def __aenter__(self) -> "Client":
        return await self.connect()

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"Client(network={self.network!r}, endpoint={self.endpoint!r})"
