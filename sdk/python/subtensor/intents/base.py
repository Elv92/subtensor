"""The ``Intent`` base: a mutation described as serializable data.

An intent is a small dataclass whose fields are JSON-native (str/int/float/bool)
so it round-trips to and from a dict without custom encoders. It knows how to
build its chain call, summarize itself, and expose a JSON schema. It does *not*
know how to sign or submit — that is the client's single execute choke point.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import MISSING, asdict, dataclass, field, fields
from typing import TYPE_CHECKING, Any, ClassVar, Literal

if TYPE_CHECKING:
    from .._substrate import Substrate

Signer = Literal["coldkey", "hotkey"]

# Field annotations are strings here (PEP 563 / `from __future__ import annotations`),
# so this maps by annotation name.
_JSON_TYPES: dict[str, str] = {
    "str": "string",
    "int": "integer",
    "float": "number",
    "bool": "boolean",
}


def _json_type(annotation: str) -> dict[str, Any]:
    """Map a (stringified) field annotation to a JSON Schema fragment.

    Handles ``Optional[X]`` / ``X | None`` and ``list``/``list[X]``. Raises on an
    unknown base type so a mistyped intent field fails loudly at registration
    rather than shipping a wrong schema to an agent.
    """
    a = annotation.strip()
    if a.startswith("Optional[") and a.endswith("]"):
        a = a[len("Optional[") : -1].strip()
    if a.endswith("| None"):
        a = a[: -len("| None")].strip()
    if a == "list" or a.startswith("list["):
        schema: dict[str, Any] = {"type": "array"}
        if a.startswith("list["):
            schema["items"] = _json_type(a[len("list[") : -1].strip())
        return schema
    if a == "dict" or a.startswith("dict["):
        return {"type": "object"}
    if a in _JSON_TYPES:
        return {"type": _JSON_TYPES[a]}
    raise ValueError(f"Unsupported intent field annotation for JSON schema: {annotation!r}")


@dataclass
class Intent(ABC):
    """Base class for all state-changing operations.

    Subclasses set the class vars ``op`` (stable machine name) and ``signer``
    ("coldkey" or "hotkey"), declare their parameters as dataclass fields, and
    implement ``build`` and ``summary``.
    """

    op: ClassVar[str]
    signer: ClassVar[Signer] = "coldkey"
    # The chain call(s) this intent wraps, as (pallet, call_function) pairs. Used by
    # the codegen coverage gate to prove every chain call has a deliberate status.
    wraps: ClassVar[tuple[tuple[str, str], ...]] = ()

    @abstractmethod
    async def build(self, substrate: "Substrate", wallet: "Any"):
        """Compose and return the chain call for this intent.

        Returns the composed call, or a :class:`BuiltCall` when the intent needs to
        surface build-time data (e.g. a reveal round) into the execution result.

        ``wallet`` is provided because some operations need the signer's own keys
        as call parameters (e.g. the hotkey being registered). Intents that don't
        need it ignore it. It is never stored on the intent.
        """

    @abstractmethod
    def summary(self) -> str:
        """One-line human description of what this intent will do."""

    async def effects(self, substrate: "Substrate", signer_address: str) -> list[str]:
        """Predicted effects, shown by ``plan``. Defaults to the summary."""
        return [self.summary()]

    async def warnings(self, substrate: "Substrate", signer_address: str) -> list[str]:
        """Non-fatal cautions surfaced by ``plan`` (e.g. dust amounts)."""
        return []

    def spend_tao(self) -> float:
        """TAO this intent moves out of / destroys from the signer, for policy checks.

        Return ``float("inf")`` for intents that move or burn an amount the SDK
        can't cheaply bound (so a spend cap blocks them until raised), 0 for
        intents that move no TAO. Default is 0 — override when value leaves.
        """
        return 0.0

    def touches_netuids(self) -> list[int]:
        """Every netuid this intent acts on, for policy allowlists.

        Defaults to the intent's ``netuid`` field if present, else none. Intents
        that span origin+destination override to return both.
        """
        netuid = getattr(self, "netuid", None)
        return [netuid] if netuid is not None else []

    def affects_all_subnets(self) -> bool:
        """True if the intent acts across every subnet (so any allowlist must fail it)."""
        return False

    # Serialization ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"op": self.op, **asdict(self)}

    @classmethod
    def from_args(cls, args: dict[str, Any]) -> "Intent":
        allowed = {f.name for f in fields(cls)}
        unknown = set(args) - allowed - {"op"}
        if unknown:
            raise ValueError(f"Unknown arguments for {cls.op}: {sorted(unknown)}")
        return cls(**{k: v for k, v in args.items() if k in allowed})

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        """JSON Schema for this intent's parameters (for tool/agent discovery)."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for f in fields(cls):
            properties[f.name] = _json_type(str(f.type))
            if f.default is MISSING and f.default_factory is MISSING:
                required.append(f.name)
        return {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }


@dataclass
class BuiltCall:
    """A composed call plus structured extras to surface into the result.

    Returned from ``Intent.build`` when an intent computes data at build time that
    the caller should see in the execution result (e.g. a weights reveal round).
    """

    call: Any
    extras: dict[str, Any] = field(default_factory=dict)
