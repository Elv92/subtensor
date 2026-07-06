"""Multisig: dispatch a call from a shared-custody composite account.

A multisig account is a deterministic address derived from a set of signatories
and a threshold; a call runs from it once ``threshold`` of them approve. The flow:

  1. the first signer calls ``multisig_execute`` (or ``multisig_approve``) with
     ``timepoint=None`` to open the operation;
  2. other signers ``multisig_approve`` with the opening ``timepoint`` (from the
     ``multisig`` read) until ``threshold - 1`` approvals exist;
  3. the final signer calls ``multisig_execute`` with the ``timepoint`` and the
     full inner call, which runs it.

For a 1-of-N multisig, ``multisig_threshold_1`` dispatches immediately. The inner
call is given as ``{"op": <intent op>, ...args}`` (like a batch child), and its
args must be fully explicit — it dispatches as the multisig account, not the
signer's wallet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from scalecodec.utils.ss58 import ss58_decode

from ..signing import public_view
from .._generated import calls
from .base import BuiltCall, Intent
from .registry import build as build_intent
from .registry import register


def _sorted_signatories(signatories: list) -> list:
    """Other signatories must be sorted by raw account id (not ss58 text) and unique."""
    return sorted(set(signatories), key=lambda s: bytes.fromhex(ss58_decode(s)))


async def _compose_inner(substrate, wallet: Any, spec: dict):
    """Build the inner call from a ``{"op": ..., ...args}`` spec (like a batch child)."""
    args = dict(spec)
    op = args.pop("op", None)
    if not op:
        raise ValueError("multisig inner call needs an 'op' key")
    built = await build_intent(op, args).build(substrate, wallet)
    return built.call if isinstance(built, BuiltCall) else built


def _timepoint(value: Optional[dict]):
    """Normalize a timepoint dict to the chain's ``{height, index}`` (or None)."""
    if value is None:
        return None
    return {"height": int(value["height"]), "index": int(value["index"])}


@register
@dataclass
class MultisigThreshold1(Intent):
    """Dispatch a 1-of-N multisig call immediately (single approval)."""

    op = "multisig_threshold_1"
    signer = "coldkey"
    wraps = (("Multisig", "as_multi_threshold_1"),)

    other_signatories: list
    call: dict

    async def build(self, substrate, wallet: Any):
        inner = await _compose_inner(substrate, wallet, self.call)
        return await substrate.compose(
            calls.Multisig.as_multi_threshold_1(
                other_signatories=_sorted_signatories(self.other_signatories), call=inner
            )
        )

    def summary(self) -> str:
        return f"multisig (1-of-N) dispatch {self.call.get('op')}"


@register
@dataclass
class MultisigExecute(Intent):
    """Approve and, if the threshold is met, execute a multisig call (final approval)."""

    op = "multisig_execute"
    signer = "coldkey"
    wraps = (("Multisig", "as_multi"),)

    threshold: int
    other_signatories: list
    call: dict
    timepoint: Optional[dict] = None  # None for the first approval, else {height, index}

    async def build(self, substrate, wallet: Any):
        inner = await _compose_inner(substrate, wallet, self.call)
        max_weight = await substrate.estimate_weight(inner, public_view(wallet, "coldkey"))
        return await substrate.compose(
            calls.Multisig.as_multi(
                threshold=self.threshold,
                other_signatories=_sorted_signatories(self.other_signatories),
                maybe_timepoint=_timepoint(self.timepoint),
                call=inner,
                max_weight=max_weight,
            )
        )

    def summary(self) -> str:
        return (
            f"multisig {self.threshold}-of-{len(self.other_signatories) + 1} "
            f"execute {self.call.get('op')}"
        )


@register
@dataclass
class MultisigApprove(Intent):
    """Register approval for a multisig call by its hash (non-final approvals)."""

    op = "multisig_approve"
    signer = "coldkey"
    wraps = (("Multisig", "approve_as_multi"),)

    threshold: int
    other_signatories: list
    call: dict
    timepoint: Optional[dict] = None

    async def build(self, substrate, wallet: Any):
        inner = await _compose_inner(substrate, wallet, self.call)
        max_weight = await substrate.estimate_weight(inner, public_view(wallet, "coldkey"))
        return await substrate.compose(
            calls.Multisig.approve_as_multi(
                threshold=self.threshold,
                other_signatories=_sorted_signatories(self.other_signatories),
                maybe_timepoint=_timepoint(self.timepoint),
                call_hash=inner.call_hash,
                max_weight=max_weight,
            )
        )

    def summary(self) -> str:
        return (
            f"multisig {self.threshold}-of-{len(self.other_signatories) + 1} "
            f"approve {self.call.get('op')}"
        )


@register
@dataclass
class MultisigCancel(Intent):
    """Cancel an ongoing multisig operation (only the original depositor may)."""

    op = "multisig_cancel"
    signer = "coldkey"
    wraps = (("Multisig", "cancel_as_multi"),)

    threshold: int
    other_signatories: list
    call: dict
    timepoint: dict  # the opening timepoint {height, index}

    async def build(self, substrate, wallet: Any):
        inner = await _compose_inner(substrate, wallet, self.call)
        return await substrate.compose(
            calls.Multisig.cancel_as_multi(
                threshold=self.threshold,
                other_signatories=_sorted_signatories(self.other_signatories),
                timepoint=_timepoint(self.timepoint),
                call_hash=inner.call_hash,
            )
        )

    def summary(self) -> str:
        return f"cancel multisig operation for {self.call.get('op')}"
