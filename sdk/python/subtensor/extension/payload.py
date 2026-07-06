"""Build SignerPayloadJSON objects for browser extension signing."""

from __future__ import annotations

from typing import Any, Optional


def _as_int(value: Any) -> int:
    if hasattr(value, "value"):
        return int(value.value)
    return int(value)


def _hex_bytes(data: bytes | bytearray | str) -> str:
    if isinstance(data, str):
        text = data.removeprefix("0x")
        return "0x" + text
    return "0x" + bytes(data).hex()


def _hash_hex(value: Any) -> str:
    if isinstance(value, str):
        return value if value.startswith("0x") else f"0x{value}"
    if isinstance(value, (bytes, bytearray)):
        return _hex_bytes(value)
    if hasattr(value, "hex"):
        return _hex_bytes(value.hex())
    return _hex_bytes(str(value).removeprefix("0x"))


def _compact_hex(runtime: Any, value: int) -> str:
    compact = runtime.runtime_config.create_scale_object("Compact")
    compact.encode(_as_int(value))
    return _hex_bytes(compact.data.data)


async def build_signer_payload_json(
    substrate: Any,
    *,
    call: Any,
    address: str,
    era: Any,
    nonce: int,
    tip: int = 0,
    tip_asset_id: Optional[int] = None,
) -> dict[str, Any]:
    """Build the JSON payload expected by Polkadot-compatible extension signers."""
    runtime = await substrate.init_runtime()
    genesis_hash = await substrate.get_block_hash(0)

    if not era:
        era = "00"

    if era == "00":
        block_hash = genesis_hash
        era_hex = "0x00"
    else:
        era_obj = runtime.runtime_config.create_scale_object("Era")
        if isinstance(era, dict) and "current" not in era and "phase" not in era:
            era["current"] = await substrate.get_block_number(await substrate.get_chain_finalised_head())
        era_obj.encode(era)
        era_hex = _hex_bytes(era_obj.data.data)
        block_hash = await substrate.get_block_hash(block_id=era_obj.birth(era.get("current")))

    call_hex = str(call.data)
    if not call_hex.startswith("0x"):
        call_hex = "0x" + call_hex

    signed_extensions: list[str] = []
    metadata = runtime.metadata[1][1]["extrinsic"]
    if "signed_extensions" in metadata:
        for entry in metadata["signed_extensions"]:
            identifier = entry.get("identifier") if isinstance(entry, dict) else None
            if isinstance(identifier, str):
                signed_extensions.append(identifier)

    spec_version = _as_int(runtime.runtime_version)
    tx_version = _as_int(runtime.transaction_version)
    extrinsic_version = _as_int(metadata["version"])

    payload: dict[str, Any] = {
        "address": address,
        "blockHash": _hash_hex(block_hash),
        "genesisHash": _hash_hex(genesis_hash),
        "method": call_hex,
        "nonce": _compact_hex(runtime, nonce),
        "specVersion": _hex_bytes(spec_version.to_bytes(4, "little")),
        "tip": _compact_hex(runtime, tip),
        "transactionVersion": _hex_bytes(tx_version.to_bytes(4, "little")),
        "era": era_hex,
        "version": extrinsic_version,
    }
    if signed_extensions:
        payload["signedExtensions"] = signed_extensions

    if tip_asset_id is not None:
        payload["assetId"] = _compact_hex(runtime, tip_asset_id)
    if "CheckMetadataHash" in signed_extensions:
        payload["mode"] = "0x00"
        payload["metadataHash"] = "0x"

    return payload
