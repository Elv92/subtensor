"""Thin async wrapper over ``AsyncSubstrateInterface``.

This is the only module that talks to the transport library directly. It handles
connection lifecycle, storage/constant/runtime-API reads, and turning a composed
call into a typed :class:`ExtrinsicResult`.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Optional

from ._transport import AsyncSubstrateInterface
from ._transport.errors import SubstrateRequestException
from .balance import Balance
from .result import ChainError, ConnectionNotReady, ExtrinsicResult
from .settings import DEFAULT_ERA_PERIOD, SS58_FORMAT, TYPE_REGISTRY


class Substrate:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self._substrate: Optional[AsyncSubstrateInterface] = None

    @property
    def raw(self) -> AsyncSubstrateInterface:
        if self._substrate is None:
            raise ConnectionNotReady(
                "Client connection is not open. Use `async with Client(...)` "
                "or call `await client.connect()` first."
            )
        return self._substrate

    async def connect(self) -> None:
        if self._substrate is not None:
            return
        substrate = AsyncSubstrateInterface(
            url=self.endpoint,
            ss58_format=SS58_FORMAT,
            type_registry=TYPE_REGISTRY,
            use_remote_preset=True,
            chain_name="Bittensor",
        )
        await substrate.initialize()
        self._substrate = substrate

    async def close(self) -> None:
        if self._substrate is not None:
            await self._substrate.close()
            self._substrate = None

    # Reads ------------------------------------------------------------------

    async def block_hash(self, block: Optional[int] = None) -> str:
        try:
            if block is None:
                return await self.raw.get_chain_head()
            return await self.raw.get_block_hash(block)
        except SubstrateRequestException as error:
            raise ChainError(str(error)) from error

    async def block_number(self) -> int:
        try:
            return await self.raw.get_block_number(None)
        except SubstrateRequestException as error:
            raise ChainError(str(error)) from error

    async def query(
        self,
        module: str,
        storage_function: str,
        params: Optional[list] = None,
        block_hash: Optional[str] = None,
    ) -> Any:
        try:
            result = await self.raw.query(
                module=module,
                storage_function=storage_function,
                params=params or [],
                block_hash=block_hash,
            )
        except SubstrateRequestException as error:
            raise ChainError(str(error)) from error
        return result.value

    async def query_map(
        self,
        module: str,
        storage_function: str,
        params: Optional[list] = None,
        block_hash: Optional[str] = None,
    ) -> list[tuple[Any, Any]]:
        try:
            result = await self.raw.query_map(
                module=module,
                storage_function=storage_function,
                params=params or [],
                block_hash=block_hash,
            )
            return [
                (_unwrap_key(k), v.value if hasattr(v, "value") else v) async for k, v in result
            ]
        except SubstrateRequestException as error:
            raise ChainError(str(error)) from error

    async def query_batch(
        self,
        module: str,
        storage_function: str,
        param_sets: list[list],
        block_hash: Optional[str] = None,
    ) -> list[Any]:
        """Read the same storage map for many keys in a single RPC round-trip.

        ``param_sets`` is a list of parameter lists (one per key); results are
        returned in the same order. Building the storage keys is local work against
        cached runtime metadata, so only one network request is made.
        """
        if not param_sets:
            return []
        if block_hash is None:
            block_hash = await self.block_hash()
        try:
            keys = [
                await self.raw.create_storage_key(
                    module, storage_function, params, block_hash=block_hash
                )
                for params in param_sets
            ]
            results = await self.raw.query_multi(keys, block_hash=block_hash)
        except SubstrateRequestException as error:
            raise ChainError(str(error)) from error
        by_key = {tuple(key.params): value for key, value in results}
        return [_scale_value(by_key.get(tuple(params))) for params in param_sets]

    async def runtime_call(
        self,
        api: str,
        method: str,
        params: list,
        block_hash: Optional[str] = None,
    ) -> Any:
        try:
            result = await self.raw.runtime_call(api, method, params, block_hash=block_hash)
        except SubstrateRequestException as error:
            raise ChainError(str(error)) from error
        return result.value if hasattr(result, "value") else result

    async def constant(self, module: str, name: str) -> Any:
        try:
            result = await self.raw.get_constant(module, name)
        except SubstrateRequestException as error:
            raise ChainError(str(error)) from error
        return result.value if hasattr(result, "value") else result

    async def blocks(self, *, finalized: bool = False) -> AsyncIterator[dict]:
        """Stream decoded block headers as they are produced (or finalized).

        The transport's subscription is handler-based; this adapts it into an
        async iterator via a queue so callers can just ``async for`` over it.
        The underlying subscription is cancelled when iteration stops.
        """
        queue: asyncio.Queue = asyncio.Queue()

        async def handler(block: dict) -> None:
            await queue.put(block)

        subscription = asyncio.create_task(
            self.raw.subscribe_block_headers(handler, finalized_only=finalized)
        )
        try:
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {getter, subscription}, return_when=asyncio.FIRST_COMPLETED
                )
                if getter in done:
                    yield getter.result()
                    continue
                getter.cancel()
                error = subscription.exception()
                if error is not None:
                    raise ChainError(str(error)) from error
                return
        finally:
            subscription.cancel()

    async def compose(self, call):
        """Compose a chain call from a generated ``Call`` (module, function, params)."""
        module, function, params = call
        return await self.raw.compose_call(
            call_module=module, call_function=function, call_params=params
        )

    async def estimate_fee(self, call, keypair) -> Balance:
        """Estimate the fee for a call without submitting it (no signature needed)."""
        info = await self.raw.get_payment_info(call=call, keypair=keypair)
        fee = info.get("partial_fee", info.get("partialFee", 0))
        return Balance.from_rao(int(fee))

    async def estimate_weight(self, call, keypair) -> dict:
        """The dispatch weight ``{ref_time, proof_size}`` of a call, for multisig max_weight."""
        info = await self.raw.get_payment_info(call=call, keypair=keypair)
        weight = info.get("weight") or {}
        return {
            "ref_time": int(weight.get("ref_time", 0)),
            "proof_size": int(weight.get("proof_size", 0)),
        }

    # Writes -----------------------------------------------------------------

    async def mev_next_key(self) -> Optional[bytes]:
        """The MEV Shield ML-KEM-768 public key from ``NextKey`` storage (rotates per block)."""
        value = await self.query("MevShield", "NextKey")
        if not value:
            return None
        if isinstance(value, str):
            return bytes.fromhex(value.removeprefix("0x"))
        return bytes(value)

    async def sign_extrinsic(self, call, keypair, *, nonce: int, period: int) -> tuple[bytes, str]:
        """Create a signed extrinsic and return its (raw bytes, 0x-hex hash) without submitting.

        Used to build the inner extrinsic for MEV-shielded submission, which is
        encrypted and carried inside ``MevShield.submit_encrypted``.
        """
        extrinsic = await self.raw.create_signed_extrinsic(
            call=call, keypair=keypair, nonce=nonce, era={"period": period}
        )
        return bytes(extrinsic.data.data), "0x" + extrinsic.extrinsic_hash.hex()

    async def submit(
        self,
        call,
        keypair,
        *,
        nonce: Optional[int] = None,
        period: Optional[int] = DEFAULT_ERA_PERIOD,
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = True,
    ) -> ExtrinsicResult:
        """Sign, submit, and wait for a call, returning a typed result.

        The nonce is fetched via ``get_account_next_index`` (unless one is passed
        explicitly, as for MEV-shielded submission where the outer/inner nonces must
        be pinned) so the outer/inner nonces of a call are deterministic. On any
        submission failure the account's cached next-index is cleared, because a
        failed submit does not consume the nonce on-chain and a stale cached value
        would wedge every subsequent submit for that account into future-nonce limbo.
        """
        substrate = self.raw
        if nonce is None:
            nonce = await substrate.get_account_next_index(keypair.ss58_address)
        extrinsic_kwargs: dict[str, Any] = {"call": call, "keypair": keypair, "nonce": nonce}
        if period is not None:
            extrinsic_kwargs["era"] = {"period": period}

        extrinsic = await substrate.create_signed_extrinsic(**extrinsic_kwargs)

        try:
            receipt = await substrate.submit_extrinsic(
                extrinsic=extrinsic,
                wait_for_inclusion=wait_for_inclusion,
                wait_for_finalization=wait_for_finalization,
            )
        except Exception as error:
            # Any failure between signing and inclusion (RPC rejection, dropped
            # websocket, cancellation) leaves the nonce unconsumed on-chain.
            substrate.clear_nonce_cache_for_account(keypair.ss58_address)
            if not isinstance(error, SubstrateRequestException):
                raise ChainError(str(error)) from error
            return ExtrinsicResult(
                success=False,
                message=str(error),
                error=ChainError(str(error)),
            )

        return await self._result_from_receipt(receipt, wait_for_inclusion or wait_for_finalization)

    async def submit_signed(
        self,
        extrinsic,
        keypair,
        *,
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = True,
    ) -> ExtrinsicResult:
        """Submit an already-signed extrinsic and return a typed result.

        Used when the extrinsic is built elsewhere (e.g. a multisig approval), so
        the same receipt-to-``ExtrinsicResult`` decoding and nonce-cache hygiene as
        :meth:`submit` apply without this layer re-signing the call.
        """
        try:
            receipt = await self.raw.submit_extrinsic(
                extrinsic=extrinsic,
                wait_for_inclusion=wait_for_inclusion,
                wait_for_finalization=wait_for_finalization,
            )
        except Exception as error:
            self.raw.clear_nonce_cache_for_account(keypair.ss58_address)
            if not isinstance(error, SubstrateRequestException):
                raise ChainError(str(error)) from error
            return ExtrinsicResult(success=False, message=str(error), error=ChainError(str(error)))

        return await self._result_from_receipt(receipt, wait_for_inclusion or wait_for_finalization)

    async def _result_from_receipt(self, receipt, waited: bool) -> ExtrinsicResult:
        """Turn a submission receipt into a typed :class:`ExtrinsicResult`."""
        if not waited:
            return ExtrinsicResult(success=True, message="Submitted (not waiting).")

        if await receipt.is_success:
            return ExtrinsicResult(
                success=True,
                message="Success",
                block_hash=getattr(receipt, "block_hash", None),
                fee=Balance.from_rao(await receipt.total_fee_amount),
                events=list(await receipt.triggered_events),
            )

        error_message = await receipt.error_message
        name = None
        if isinstance(error_message, dict):
            name = error_message.get("name")
            text = error_message.get("docs") or error_message.get("name") or str(error_message)
            text = " ".join(text) if isinstance(text, list) else str(text)
        else:
            text = str(error_message)
        return ExtrinsicResult(
            success=False,
            message=text,
            error=ChainError(text, name),
        )

    # Multisig ---------------------------------------------------------------

    def multisig_account(self, signatories: list[str], threshold: int):
        """Derive the deterministic multisig ``MultiAccountId`` for a signer set."""
        return self.raw.generate_multisig_account(signatories, threshold)

    async def submit_multisig(
        self,
        call,
        keypair,
        multisig_account,
        *,
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = True,
    ) -> ExtrinsicResult:
        """Record one signatory's approval of ``call`` for a multisig account.

        The transport inspects on-chain approval state and composes
        ``approve_as_multi`` (not yet at threshold) or ``as_multi`` (this approval
        reaches the threshold, so the inner call executes). ``call`` must be a
        composed call (see :meth:`compose`).
        """
        try:
            extrinsic = await self.raw.create_multisig_extrinsic(call, keypair, multisig_account)
        except SubstrateRequestException as error:
            raise ChainError(str(error)) from error
        return await self.submit_signed(
            extrinsic,
            keypair,
            wait_for_inclusion=wait_for_inclusion,
            wait_for_finalization=wait_for_finalization,
        )


def _unwrap_key(key):
    """query_map keys arrive as a scalar or a length-1 tuple; normalize to a scalar."""
    if isinstance(key, (tuple, list)) and len(key) == 1:
        return key[0]
    return key


def _scale_value(value):
    """Unwrap a ScaleType (has `.value`) or pass a plain value through."""
    return value.value if hasattr(value, "value") else value
