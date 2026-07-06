"""Subnet-owner hyperparameters: the ``sudo set`` a subnet owner needs.

The AdminUtils pallet's ``sudo_set_*`` calls are mostly root-only, but a subset is
settable by the subnet owner for their own subnet. This exposes exactly that
owner-settable subset through one ``SetHyperparameter`` intent, keyed by a stable
name (the same names btcli uses). Root-only params, the enum-valued
``recycle_or_burn``, multi-value ``alpha_values``, and ``sn_owner_hotkey`` are left
to the raw-call escape hatch.

Read current values back with the ``subnet_hyperparameters`` read.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._generated import calls
from .base import Intent
from .registry import register

# name -> (AdminUtils setter, value is boolean). Every setter takes (netuid, value).
OWNER_HYPERPARAMETERS: dict[str, tuple[str, bool]] = {
    "immunity_period": ("sudo_set_immunity_period", False),
    "min_allowed_weights": ("sudo_set_min_allowed_weights", False),
    "weights_version": ("sudo_set_weights_version_key", False),
    "activity_cutoff": ("sudo_set_activity_cutoff", False),
    "min_burn": ("sudo_set_min_burn", False),
    "bonds_moving_avg": ("sudo_set_bonds_moving_average", False),
    "serving_rate_limit": ("sudo_set_serving_rate_limit", False),
    "commit_reveal_period": ("sudo_set_commit_reveal_weights_interval", False),
    "max_allowed_uids": ("sudo_set_max_allowed_uids", False),
    "burn_increase_mult": ("sudo_set_burn_increase_mult", False),
    "burn_half_life": ("sudo_set_burn_half_life", False),
    "commit_reveal_weights_enabled": ("sudo_set_commit_reveal_weights_enabled", True),
    "liquid_alpha_enabled": ("sudo_set_liquid_alpha_enabled", True),
    "network_pow_registration_allowed": ("sudo_set_network_pow_registration_allowed", True),
    "yuma3_enabled": ("sudo_set_yuma3_enabled", True),
    "bonds_reset_enabled": ("sudo_set_bonds_reset_enabled", True),
    "transfers_enabled": ("sudo_set_toggle_transfer", True),
    "owner_cut_enabled": ("sudo_set_owner_cut_enabled", True),
    "owner_cut_auto_lock_enabled": ("sudo_set_owner_cut_auto_lock_enabled", True),
}


@register
@dataclass
class SetHyperparameter(Intent):
    """Set an owner-settable subnet hyperparameter (btcli ``sudo set``).

    ``name`` is one of ``OWNER_HYPERPARAMETERS``; ``value`` is the numeric value
    (boolean hyperparameters take 0/1). The signer must be the subnet owner.
    """

    op = "set_hyperparameter"
    signer = "coldkey"
    wraps = tuple(("AdminUtils", method) for method, _ in OWNER_HYPERPARAMETERS.values())

    netuid: int
    name: str
    value: int

    def __post_init__(self):
        if self.name not in OWNER_HYPERPARAMETERS:
            raise ValueError(
                f"unknown or owner-unsettable hyperparameter {self.name!r}; "
                f"settable: {sorted(OWNER_HYPERPARAMETERS)}"
            )

    async def build(self, substrate, wallet: Any):
        method, is_bool = OWNER_HYPERPARAMETERS[self.name]
        value: Any = bool(self.value) if is_bool else int(self.value)
        return await substrate.compose(getattr(calls.AdminUtils, method)(self.netuid, value))

    def summary(self) -> str:
        return f"set hyperparameter {self.name}={self.value} on netuid {self.netuid}"
