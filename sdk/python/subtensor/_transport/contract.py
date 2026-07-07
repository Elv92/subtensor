"""The transport's typed result shapes.

These dataclasses are the values the transport hands to the SDK: plain,
eagerly-populated data — no lazy awaitable properties, no duck typing, no SCALE
objects. Everything here is JSON-native or bytes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SignedExtrinsic:
    """A signed extrinsic ready for submission."""

    data: bytes  # full SCALE-encoded extrinsic (length-prefixed)
    extrinsic_hash: str  # 0x-hex blake2b-256 of ``data``

    @property
    def data_hex(self) -> str:
        return "0x" + self.data.hex()


@dataclass
class MultisigAccount:
    """A deterministic multisig account derived from a signer set."""

    signatories: list[str]  # ss58, sorted the way the chain sorts them
    threshold: int
    public_key: bytes
    ss58_address: str


@dataclass
class InclusionReport:
    """Outcome of a submitted extrinsic, fully resolved at construction.

    When the submission did not wait for inclusion only ``extrinsic_hash`` is
    set. When it did, the block coordinates, triggered events, success flag,
    fee, and (on failure) the resolved error are all present.
    """

    extrinsic_hash: str
    finalized: bool = False
    block_hash: Optional[str] = None
    block_number: Optional[int] = None
    extrinsic_idx: Optional[int] = None
    is_success: Optional[bool] = None  # None when inclusion was not awaited
    total_fee_amount: Optional[int] = None
    weight: Any = None  # int (WeightV1) or {"ref_time", "proof_size"} (WeightV2)
    triggered_events: list[dict] = field(default_factory=list)
    # {"type": "Module"|"System"|"MevShield", "name": ..., "docs": ...} on failure
    error_message: Optional[dict] = None


@dataclass
class BlockData:
    """One decoded block: header plus decoded extrinsics.

    ``extrinsics`` entries are plain decoded dicts (address/call/signature...),
    or None where an extrinsic failed to decode and decoding errors were
    ignored.
    """

    header: dict
    extrinsics: list[Optional[dict]]


# --- Metadata IR (for codegen) -------------------------------------------------
#
# A minimal, transport-owned description of the runtime that sdk codegen can
# walk without touching decoded SCALE metadata objects.


@dataclass
class CallArgIR:
    name: str
    type_name: Optional[str]


@dataclass
class CallIR:
    name: str
    args: list[CallArgIR]
    docs: str


@dataclass
class ErrorIR:
    name: str
    docs: str


@dataclass
class PalletIR:
    name: str
    index: int
    calls: list[CallIR]
    errors: list[ErrorIR]
    storage_names: list[str]
    constant_names: list[str]


@dataclass
class RuntimeApiMethodIR:
    api: str
    method: str


@dataclass
class MetadataIR:
    spec_version: int
    pallets: list[PalletIR]
    runtime_api_methods: list[RuntimeApiMethodIR]
