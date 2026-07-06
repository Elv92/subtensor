"""``Plan`` and ``Policy``: preview an intent and gate it before execution.

``Plan`` is the result of a dry run — predicted fee, effects, warnings, and any
policy violations — with the built call attached (not serialized) so ``execute``
can submit exactly what was previewed. ``Policy`` is caller-supplied guardrails
enforced at the execute choke point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..balance import Balance
from .base import Intent


@dataclass
class Policy:
    """Safety limits enforced when an intent is executed.

    All limits are optional; an unset limit is not enforced.
    """

    max_fee_tao: Optional[float] = None
    max_spend_tao: Optional[float] = None
    allowed_netuids: Optional[list[int]] = None
    # Raw calls (client.submit_call) bypass intent preview, so a policy can't
    # bound their spend or netuids. They are therefore refused outright unless
    # the policy explicitly opts in.
    allow_raw_calls: bool = False

    def check(self, intent: Intent, fee: Optional[Balance]) -> list[str]:
        violations: list[str] = []
        if self.max_fee_tao is not None and fee is not None and fee.tao > self.max_fee_tao:
            violations.append(f"fee {fee.tao} TAO exceeds max_fee_tao {self.max_fee_tao}")
        spend = intent.spend_tao()
        if self.max_spend_tao is not None and spend > self.max_spend_tao:
            violations.append(f"spend {spend} TAO exceeds max_spend_tao {self.max_spend_tao}")
        if self.allowed_netuids is not None:
            allowed = set(self.allowed_netuids)
            if intent.affects_all_subnets():
                violations.append(
                    f"{intent.op} acts on all subnets, not just allowed_netuids "
                    f"{self.allowed_netuids}"
                )
            for netuid in intent.touches_netuids():
                if netuid not in allowed:
                    violations.append(
                        f"netuid {netuid} not in allowed_netuids {self.allowed_netuids}"
                    )
        return violations


@dataclass
class Plan:
    """A previewed, not-yet-submitted intent."""

    op: str
    summary: str
    signer: str
    signer_address: Optional[str]
    fee: Optional[Balance]
    effects: list[str]
    warnings: list[str]
    violations: list[str] = field(default_factory=list)
    call: Any = field(default=None, repr=False)  # built call; not serialized
    extras: dict[str, Any] = field(default_factory=dict)  # build-time data for the result

    @property
    def ok(self) -> bool:
        """True when there are no policy violations blocking execution."""
        return not self.violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "summary": self.summary,
            "signer": self.signer,
            "signer_address": self.signer_address,
            "fee_tao": self.fee.tao if self.fee is not None else None,
            "effects": self.effects,
            "warnings": self.warnings,
            "violations": self.violations,
            "ok": self.ok,
        }
