"""Dump and parse runtime metadata into a language-neutral IR.

The IR is deliberately small and JSON-serializable: it captures only what the
emitters currently use — pallet index, call names + parameter names, error names
+ docs, and storage/constant/runtime-API names. Growing coverage (e.g. typed call
params) means growing the IR, not rewriting emitters.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from typing import Any

from subtensor._transport import SubstrateConnection
from subtensor.settings import SS58_FORMAT, TYPE_REGISTRY


@dataclass
class ErrorIR:
    index: int
    name: str
    docs: str


@dataclass
class CallIR:
    name: str
    args: list[str]  # parameter names, in call order
    docs: str


@dataclass
class RuntimeApiIR:
    name: str
    methods: list[str]  # method names


@dataclass
class PalletIR:
    name: str
    index: int
    calls: list[CallIR] = field(default_factory=list)
    errors: list[ErrorIR] = field(default_factory=list)
    storage: list[str] = field(default_factory=list)  # storage item names
    constants: list[str] = field(default_factory=list)  # constant names


@dataclass
class MetadataIR:
    spec_version: int
    pallets: list[PalletIR]
    runtime_apis: list[RuntimeApiIR] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _from_transport_ir(ir) -> MetadataIR:
    """Map the transport's metadata IR into this module's (serializable) IR."""
    pallets = [
        PalletIR(
            name=pallet.name,
            index=int(pallet.index),
            calls=[
                CallIR(name=call.name, args=[arg.name for arg in call.args], docs=call.docs)
                for call in pallet.calls
            ],
            errors=[
                ErrorIR(index=error_index, name=error.name, docs=error.docs)
                for error_index, error in enumerate(pallet.errors)
            ],
            storage=list(pallet.storage_names),
            constants=list(pallet.constant_names),
        )
        for pallet in ir.pallets
    ]
    apis: dict[str, list[str]] = {}
    for method in ir.runtime_api_methods:
        apis.setdefault(method.api, []).append(method.method)
    runtime_apis = [RuntimeApiIR(name=name, methods=methods) for name, methods in apis.items()]
    return MetadataIR(
        spec_version=int(ir.spec_version), pallets=pallets, runtime_apis=runtime_apis
    )


async def dump_from_node(endpoint: str) -> MetadataIR:
    """Connect to a node and parse its current runtime metadata into the IR."""
    connection = SubstrateConnection(
        endpoint, ss58_format=SS58_FORMAT, type_registry=TYPE_REGISTRY
    )
    await connection.initialize()
    try:
        return _from_transport_ir(await connection.metadata_ir())
    finally:
        await connection.close()


def dump(endpoint: str) -> MetadataIR:
    return asyncio.run(dump_from_node(endpoint))
