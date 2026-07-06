"""Typed outcomes and errors.

Every write returns an ``ExtrinsicResult`` rather than a ``(bool, str)`` tuple.
Errors carry a machine-readable :class:`ErrorCode` and a short remediation hint so
an agent can branch on the failure and know what to try next, instead of parsing
a human sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ._generated.errors import ERRORS


class BittensorError(Exception):
    """Base class for all SDK errors."""


class ConnectionNotReady(BittensorError):
    """Raised when the client is used before its connection is opened."""


class ErrorCode(str, Enum):
    INSUFFICIENT_BALANCE = "insufficient_balance"
    RATE_LIMITED = "rate_limited"
    NOT_REGISTERED = "not_registered"
    SUBNET_NOT_EXISTS = "subnet_not_exists"
    SUBTOKEN_DISABLED = "subtoken_disabled"
    UNIT_MISMATCH = "unit_mismatch"
    INVALID_ARGUMENT = "invalid_argument"
    POLICY_VIOLATION = "policy_violation"
    UNKNOWN = "unknown"


_REMEDIATION: dict[ErrorCode, str] = {
    ErrorCode.INSUFFICIENT_BALANCE: "Fund the signing account or reduce the amount.",
    ErrorCode.RATE_LIMITED: "Wait for the rate-limit window to pass, then retry.",
    ErrorCode.NOT_REGISTERED: "Register the hotkey on this subnet first.",
    ErrorCode.SUBNET_NOT_EXISTS: "Use an existing netuid; list subnets to see valid ones.",
    ErrorCode.SUBTOKEN_DISABLED: "The subnet is not active yet; wait for start_call.",
    ErrorCode.UNIT_MISMATCH: "Match the Balance netuid to the operation's currency.",
    ErrorCode.INVALID_ARGUMENT: "Check the argument values against the operation schema.",
    ErrorCode.POLICY_VIOLATION: "The action exceeds a configured safety policy.",
    ErrorCode.UNKNOWN: "Inspect the message for details.",
}

# Exact chain error names -> semantic code. Names come from the generated metadata
# catalog (subtensor/_generated/errors.py); the `python -m codegen.check --names`
# gate asserts every name here still exists in that catalog, so a runtime rename is
# caught rather than silently degrading to UNKNOWN.
_NAME_TO_CODE: dict[str, ErrorCode] = {
    "InsufficientBalance": ErrorCode.INSUFFICIENT_BALANCE,
    "ExistentialDeposit": ErrorCode.INSUFFICIENT_BALANCE,
    "NotEnoughBalanceToStake": ErrorCode.INSUFFICIENT_BALANCE,
    "NotEnoughStake": ErrorCode.INSUFFICIENT_BALANCE,
    "NotEnoughStakeToWithdraw": ErrorCode.INSUFFICIENT_BALANCE,
    "ZeroBalanceAfterWithdrawn": ErrorCode.INSUFFICIENT_BALANCE,
    "BalanceWithdrawalError": ErrorCode.INSUFFICIENT_BALANCE,
    "HotKeyNotRegisteredInSubNet": ErrorCode.NOT_REGISTERED,
    "HotKeyNotRegisteredInNetwork": ErrorCode.NOT_REGISTERED,
    "HotKeyAccountNotExists": ErrorCode.NOT_REGISTERED,
    "SubnetNotExists": ErrorCode.SUBNET_NOT_EXISTS,
    "RootNetworkDoesNotExist": ErrorCode.SUBNET_NOT_EXISTS,
    "SubtokenDisabled": ErrorCode.SUBTOKEN_DISABLED,
}

# Substring fallback, used only when there is no exact name (e.g. the transaction
# was rejected in the pool with a JSON-RPC message rather than a module error).
_SUBSTRING_FALLBACK: tuple[tuple[str, ErrorCode], ...] = (
    ("too low", ErrorCode.INSUFFICIENT_BALANCE),
    ("insufficient", ErrorCode.INSUFFICIENT_BALANCE),
    ("not enough", ErrorCode.INSUFFICIENT_BALANCE),
    ("balance too low", ErrorCode.INSUFFICIENT_BALANCE),
    ("rate limit", ErrorCode.RATE_LIMITED),
    ("too fast", ErrorCode.RATE_LIMITED),
)


def classify_error(text: str, name: Optional[str] = None) -> ErrorCode:
    """Map a chain error to a semantic code: exact by name (rate-limit by suffix),
    falling back to substring matching only when no name is available."""
    if name:
        if name in _NAME_TO_CODE:
            return _NAME_TO_CODE[name]
        if name.endswith("RateLimitExceeded") or "RateLimit" in name:
            return ErrorCode.RATE_LIMITED
        return ErrorCode.UNKNOWN
    haystack = (text or "").lower()
    for needle, code in _SUBSTRING_FALLBACK:
        if needle in haystack:
            return code
    return ErrorCode.UNKNOWN


class ChainError(BittensorError):
    """A call was rejected or failed on-chain."""

    def __init__(
        self,
        message: str,
        name: Optional[str] = None,
        code: Optional[ErrorCode] = None,
    ):
        super().__init__(message)
        self.message = message
        self.name = name
        self.code = code or classify_error(message, name)

    @property
    def remediation(self) -> str:
        return _REMEDIATION[self.code]

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "name": self.name,
            "code": self.code.value,
            "remediation": self.remediation,
        }


def chain_error_from_dispatch(err: Any) -> ChainError:
    """Build a ChainError from a decoded ``DispatchError`` payload.

    Used for errors that arrive inside event attributes (e.g. the inner result of
    a ``Proxy.ProxyExecuted`` event) rather than as a failed extrinsic. Module
    errors are resolved to their exact name/docs via the generated catalog.
    """
    if isinstance(err, dict) and "Module" in err:
        module = err["Module"] or {}
        pallet_index = int(module.get("index", -1))
        raw = module.get("error")
        if isinstance(raw, str):
            error_index = int(raw.removeprefix("0x")[:2] or "0", 16)
        elif isinstance(raw, (list, tuple)) and raw:
            error_index = int(raw[0])
        else:
            error_index = int(raw or 0)
        info = ERRORS.get((pallet_index, error_index))
        if info:
            return ChainError(info.docs or info.name, info.name)
        return ChainError(f"module error {pallet_index}/{error_index}")
    return ChainError(str(err))


class PolicyError(BittensorError):
    """Raised when an intent violates the active safety policy at execute time."""

    def __init__(self, violations: list[str]):
        super().__init__("; ".join(violations))
        self.violations = violations
        self.code = ErrorCode.POLICY_VIOLATION


@dataclass
class ExtrinsicResult:
    """Outcome of a submitted extrinsic.

    Attributes:
        success: Whether the extrinsic executed successfully on-chain.
        message: Human-readable status.
        block_hash: Hash of the including block, when available.
        fee: Fee actually paid, when available.
        events: Triggered events, when the call waited for inclusion.
        error: The underlying chain error, if it failed.
        data: Operation-specific extras (e.g. balances before/after).
    """

    success: bool
    message: str = ""
    block_hash: Optional[str] = None
    fee: Optional["Any"] = None
    events: list = field(default_factory=list)
    error: Optional[ChainError] = None
    data: dict[str, Any] = field(default_factory=dict)

    def raise_for_failure(self) -> "ExtrinsicResult":
        """Raise the underlying ChainError if the extrinsic did not succeed."""
        if not self.success:
            raise self.error or ChainError(self.message or "Extrinsic failed.")
        return self

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"success": self.success, "message": self.message}
        if self.block_hash:
            payload["block_hash"] = self.block_hash
        if self.fee is not None:
            payload["fee_tao"] = self.fee.tao
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        if self.data:
            payload["data"] = self.data
        return payload

    def __bool__(self) -> bool:
        return self.success
