"""Per-subnet hyperparameter scalar reads (one storage value + cast)."""

from __future__ import annotations

from .._generated import storage as st
from .base import scalar_read


def _hyperparam(name: str, item, doc: str) -> None:
    scalar_read(name, item, per_netuid=True, doc=doc, category="Hyperparameters")


_hyperparam(
    "weights_rate_limit",
    st.SubtensorModule.WeightsSetRateLimit,
    "Blocks a hotkey must wait between weight sets on a subnet.",
)
_hyperparam(
    "difficulty",
    st.SubtensorModule.Difficulty,
    "Current PoW registration difficulty for a subnet.",
)
_hyperparam(
    "min_allowed_weights",
    st.SubtensorModule.MinAllowedWeights,
    "Minimum number of weights a validator must set on a subnet.",
)
_hyperparam(
    "max_weight_limit",
    st.SubtensorModule.MaxWeightsLimit,
    "Maximum allowed value for any single weight (u16) on a subnet.",
)
_hyperparam(
    "immunity_period",
    st.SubtensorModule.ImmunityPeriod,
    "Blocks a newly registered neuron is immune from deregistration.",
)
_hyperparam(
    "reveal_period",
    st.SubtensorModule.RevealPeriodEpochs,
    "Commit-reveal reveal window, in epochs, for a subnet.",
)
