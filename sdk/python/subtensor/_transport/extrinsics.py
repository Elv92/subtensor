"""Extrinsic construction and outcome resolution.

Signing side: era normalization, the signature payload, and the three signer
shapes the SDK supports — plain sync ``sign``, coroutine ``sign`` (hardware and
remote signers), and browser-extension signers exposing
``sign_extrinsic_payload`` (which take a Polkadot-JS ``SignerPayloadJSON``
instead of raw bytes).

Outcome side: the event-walk that turns a block's ``System.Events`` entries
into success/fee/weight/error for one extrinsic, including Bittensor's
MevShield failure events. This is pure logic over decoded events; fetching
lives in the facade.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Optional

from .codec import RuntimeCodec
from .contract import SignedExtrinsic
from .protocols import Keypair
from .rpc import RpcSession
from .utils.receipt import (
    build_system_error_message,
    extract_failure_details,
    extract_fallback_deposit_fee_amount,
    extract_success_weight,
    extract_total_fee_amount,
    is_extrinsic_failure_event,
    is_extrinsic_success_event,
    normalize_module_error,
)

IMMORTAL = "00"


class NonceCache:
    """Per-account next-nonce cache for pipelined submissions.

    The first request for an account asks the node (``account_nextIndex``);
    subsequent requests increment locally so concurrent submissions get
    distinct consecutive nonces. A failed submission must clear the account:
    the chain never consumed that nonce.
    """

    def __init__(self, session: RpcSession):
        self._session = session
        self._nonces: dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def next_for(self, address: str, *, use_cache: bool = True) -> int:
        if not use_cache:
            return await self._session.request("account_nextIndex", [address])
        async with self._lock:
            if address not in self._nonces:
                self._nonces[address] = await self._session.request(
                    "account_nextIndex", [address]
                )
            else:
                self._nonces[address] += 1
            return self._nonces[address]

    def pin(self, address: str, nonce: int) -> None:
        """Record an explicitly-chosen nonce as the account's latest."""
        self._nonces[address] = nonce

    def clear(self, address: str) -> None:
        self._nonces.pop(address, None)


def signer_payload_json(
    codec: RuntimeCodec,
    *,
    call: Any,
    address: str,
    era: dict | str,
    nonce: int,
    tip: int,
    tip_asset_id: Optional[int],
    genesis_hash: str,
    era_block_hash: str,
) -> dict:
    """The Polkadot-JS ``SignerPayloadJSON`` for browser-extension signers."""
    era_hex = "0x00" if era == IMMORTAL else "0x" + codec.encode_era(era).hex()
    payload: dict[str, Any] = {
        "address": address,
        "blockHash": era_block_hash,
        "genesisHash": genesis_hash,
        "method": "0x" + codec.call_data(call).hex(),
        "nonce": "0x" + codec.encode_compact(nonce).hex(),
        "specVersion": "0x" + codec.spec_version.to_bytes(4, "little").hex(),
        "tip": "0x" + codec.encode_compact(tip).hex(),
        "transactionVersion": "0x" + codec.transaction_version.to_bytes(4, "little").hex(),
        "era": era_hex,
        "version": codec.extrinsic_version,
    }
    signed_extensions = codec.signed_extension_identifiers()
    if signed_extensions:
        payload["signedExtensions"] = signed_extensions
    if tip_asset_id is not None:
        payload["assetId"] = "0x" + codec.encode_compact(tip_asset_id).hex()
    if "CheckMetadataHash" in signed_extensions:
        payload["mode"] = "0x00"
        payload["metadataHash"] = "0x"
    return payload


async def create_signed_extrinsic(
    codec: RuntimeCodec,
    call: Any,
    keypair: Keypair,
    *,
    era: dict | str,
    nonce: int,
    tip: int = 0,
    tip_asset_id: Optional[int] = None,
    genesis_hash: str,
    era_block_hash: str,
    signature: Optional[bytes | str] = None,
) -> SignedExtrinsic:
    """Sign ``call`` and assemble the extrinsic.

    ``era`` must already be normalized ("00" or a dict containing ``current``).
    ``signature`` short-circuits signing (externally-signed or fee-estimation
    paths); a 65-byte value carries the signature version in its first byte.
    """
    if signature is not None:
        if isinstance(signature, str):
            signature = bytes.fromhex(signature.removeprefix("0x"))
        if len(signature) == 65:
            signature_version, signature = signature[0], signature[1:]
        else:
            signature_version = keypair.crypto_type
    else:
        sign_extrinsic_payload = getattr(keypair, "sign_extrinsic_payload", None)
        if sign_extrinsic_payload is not None:
            payload_json = signer_payload_json(
                codec,
                call=call,
                address=keypair.ss58_address,
                era=era,
                nonce=nonce,
                tip=tip,
                tip_asset_id=tip_asset_id,
                genesis_hash=genesis_hash,
                era_block_hash=era_block_hash,
            )
            result = sign_extrinsic_payload(payload_json)
            if inspect.isawaitable(result):
                result = await result
            signature_hex = result.get("signature") if isinstance(result, dict) else None
            if not isinstance(signature_hex, str):
                raise ValueError("extension signer did not return a signature")
            signature = bytes.fromhex(signature_hex.removeprefix("0x"))
            if len(signature) == 65:
                signature_version, signature = signature[0], signature[1:]
            else:
                signature_version = keypair.crypto_type
        else:
            payload = codec.signature_payload(
                call,
                era=era,
                nonce=nonce,
                tip=tip,
                tip_asset_id=tip_asset_id,
                genesis_hash=genesis_hash,
                era_block_hash=era_block_hash,
            )
            signature_version = keypair.crypto_type
            signed = keypair.sign(payload)
            if inspect.isawaitable(signed):
                signed = await signed
            signature = signed

    assert isinstance(signature, bytes)
    public_key = keypair.public_key
    assert public_key is not None
    data, extrinsic_hash = codec.encode_signed_extrinsic(
        call,
        public_key=bytes(public_key),
        signature=signature,
        signature_version=signature_version,
        era=era,
        nonce=nonce,
        tip=tip,
        tip_asset_id=tip_asset_id,
    )
    return SignedExtrinsic(data=data, extrinsic_hash=extrinsic_hash)


def resolve_outcome(extrinsic_events: list[dict], codec: RuntimeCodec) -> dict:
    """Success/fee/weight/error for one extrinsic from its triggered events.

    Returns ``{"is_success", "total_fee_amount", "weight", "error_message"}``.
    The fee is ``TransactionPayment.TransactionFeePaid`` when present, else the
    sum of Treasury/Balances deposits (older runtimes). Failures come from
    ``System.ExtrinsicFailed`` or Bittensor's MevShield rejection events, with
    module errors resolved to their metadata name/docs.
    """
    total_fee, has_fee_paid_event = extract_total_fee_amount(extrinsic_events)
    is_success: Optional[bool] = None
    weight: Any = None
    error_message: Optional[dict] = None
    possible_success = False

    for event in extrinsic_events:
        if is_extrinsic_success_event(event):
            possible_success = True
            weight = extract_success_weight(event)
        elif is_extrinsic_failure_event(event):
            possible_success = False
            is_success = False
            details = extract_failure_details(event)
            if details["has_weight"]:
                weight = details["weight"]
            if details["error_message"] is not None:
                error_message = details["error_message"]
                continue
            dispatch_error = details["dispatch_error"]
            if dispatch_error is None:
                continue
            module_error = normalize_module_error(dispatch_error)
            if module_error is not None:
                error_message = codec.module_error(
                    module_error["module_index"], module_error["error_index"]
                )
            else:
                error_message = build_system_error_message(dispatch_error)
        elif not has_fee_paid_event:
            total_fee += extract_fallback_deposit_fee_amount(event)

    if possible_success and error_message is None:
        is_success = True
    return {
        "is_success": bool(is_success),
        "total_fee_amount": total_fee,
        "weight": weight,
        "error_message": error_message,
    }
