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

from subtensor._transport import AsyncSubstrateInterface
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


def _docs(item) -> str:
    docs = getattr(item, "docs", None) or []
    return " ".join(d.strip() for d in docs).strip()


def parse_runtime(runtime) -> MetadataIR:
    """Build the IR from a transport ``Runtime`` object."""
    pallets: list[PalletIR] = []
    for pallet in runtime.metadata.pallets:
        index = int(pallet.value["index"])

        errors: list[ErrorIR] = []
        for error_index, error in enumerate(pallet.errors or []):
            errors.append(ErrorIR(index=error_index, name=error.name, docs=_docs(error)))

        calls: list[CallIR] = []
        for call in pallet.calls or []:
            args = [arg.name for arg in (call.args or [])]
            calls.append(CallIR(name=call.name, args=args, docs=_docs(call)))

        # Skip pseudo-entries like `:__STORAGE_VERSION__:`.
        storage = [item.name for item in (pallet.storage or []) if ":" not in item.name]
        constants = [constant.name for constant in (pallet.constants or [])]

        pallets.append(
            PalletIR(
                name=pallet.name,
                index=index,
                calls=calls,
                errors=errors,
                storage=storage,
                constants=constants,
            )
        )

    runtime_apis: list[RuntimeApiIR] = []
    metadata_v15 = getattr(runtime, "metadata_v15", None)
    if metadata_v15 is not None:
        v15 = metadata_v15.value[1]["V15"]
        for api in v15.get("apis", []):
            methods = [method["name"] for method in api.get("methods", [])]
            runtime_apis.append(RuntimeApiIR(name=api["name"], methods=methods))

    return MetadataIR(
        spec_version=int(runtime.runtime_version),
        pallets=pallets,
        runtime_apis=runtime_apis,
    )


async def dump_from_node(endpoint: str) -> MetadataIR:
    """Connect to a node and parse its current runtime metadata into the IR."""
    substrate = AsyncSubstrateInterface(
        url=endpoint,
        ss58_format=SS58_FORMAT,
        type_registry=TYPE_REGISTRY,
        use_remote_preset=True,
        chain_name="Bittensor",
    )
    await substrate.initialize()
    try:
        runtime = await substrate.init_runtime()
        return parse_runtime(runtime)
    finally:
        await substrate.close()


def dump(endpoint: str) -> MetadataIR:
    return asyncio.run(dump_from_node(endpoint))
