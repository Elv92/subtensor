"""Light metagraph: every neuron on a subnet in one runtime-API call.

For a single value (e.g. one hotkey's uid) use the generic accessor:
``client.query(storage.SubtensorModule.Uids, [netuid, hotkey])``. This module
only provides the aggregating fast path; it does not model axon/dendrite
endpoints (this SDK does not serve or query the neuron network layer).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ._generated.runtime_apis import NeuronInfoRuntimeApi
from ._substrate import Substrate
from .balance import Balance


@dataclass
class Neuron:
    """One registered neuron, as reported by the chain's runtime API.

    ``raw`` carries the full decoded record (axon info, rank/trust/consensus,
    weights when ``lite=False``, ...) for anything not lifted into a field.
    """

    uid: int
    hotkey: str
    coldkey: str
    active: bool
    validator_permit: bool
    last_update: int
    total_stake: Balance
    raw: dict = field(repr=False)


class Neurons:
    def __init__(self, substrate: Substrate):
        self._s = substrate

    async def all(
        self, netuid: int, block: Optional[int] = None, *, lite: bool = True
    ) -> list[Neuron]:
        """Every neuron on a subnet in ONE runtime-API call (the metagraph fast path).

        ``lite=True`` (default) omits per-neuron weights/bonds, which is far
        smaller and what almost every caller wants.
        """
        block_hash = await self._s.block_hash(block)
        method = NeuronInfoRuntimeApi.get_neurons_lite if lite else NeuronInfoRuntimeApi.get_neurons
        records = await self._s.runtime_call(*method, [netuid], block_hash=block_hash)
        neurons = []
        for record in records or []:
            stake_rao = sum(int(amount) for _, amount in record.get("stake") or [])
            neurons.append(
                Neuron(
                    uid=int(record["uid"]),
                    hotkey=str(record["hotkey"]),
                    coldkey=str(record["coldkey"]),
                    active=bool(record["active"]),
                    validator_permit=bool(record["validator_permit"]),
                    last_update=int(record["last_update"]),
                    total_stake=Balance.from_rao(stake_rao, netuid),
                    raw=record,
                )
            )
        return sorted(neurons, key=lambda n: n.uid)
