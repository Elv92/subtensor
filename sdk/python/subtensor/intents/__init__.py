"""Declarative intents: mutations as serializable, plannable, policy-gated data.

Importing this package registers every intent. Use the concrete intent classes
directly, or discover/build them by name via the registry helpers.
"""

from .association import AssociateEvmKey, AssociateHotkey
from .base import Intent
from .batch import Batch
from .children import DecreaseTake, IncreaseTake, SetChildkeyTake, SetChildren, SetTake
from .coldkey import (
    AnnounceColdkeySwap,
    ClearColdkeySwapAnnouncement,
    DisputeColdkeySwap,
    SwapColdkeyAnnounced,
)
from .crowdloan import (
    ContributeCrowdloan,
    CreateCrowdloan,
    DissolveCrowdloan,
    FinalizeCrowdloan,
    RefundCrowdloan,
    SetCrowdloanMaxContribution,
    UpdateCrowdloanCap,
    UpdateCrowdloanEnd,
    UpdateCrowdloanMinContribution,
    WithdrawCrowdloan,
)
from .governance import (
    SenateVote,
    SetMechanismCount,
    SetMechanismEmissionSplit,
    StakeBurn,
    TrimSubnet,
    UpdateSymbol,
)
from .hyperparameters import OWNER_HYPERPARAMETERS, SetHyperparameter
from .identity import SetIdentity, SetSubnetIdentity
from .leasing import RegisterLeasedNetwork, TerminateLease
from .liquidity import AddLiquidity, ModifyLiquidity, RemoveLiquidity
from .lock import LockStake, MoveLock, SetPerpetualLock
from .multisig import (
    MultisigApprove,
    MultisigCancel,
    MultisigExecute,
    MultisigThreshold1,
)
from .plan import Plan, Policy
from .registry import REGISTRY, build, list_tools, register
from .registration import (
    BurnedRegister,
    ClaimRoot,
    RegisterSubnet,
    RootRegister,
    SetRootClaimType,
    StartCall,
    SwapHotkey,
)
from .serving import ResetAxon, ServeAxon, ServeAxonTls, ServePrometheus
from .staking import (
    AddStake,
    AddStakeLimit,
    MoveStake,
    RemoveStake,
    RemoveStakeLimit,
    SetAutoStake,
    SwapStake,
    TransferStake,
    UnstakeAll,
    UnstakeAllAlpha,
)
from .proxy import (
    PROXY_TYPES,
    AddProxy,
    CreatePureProxy,
    ExecuteProxyAnnounced,
    KillPureProxy,
    RemoveProxies,
    RemoveProxy,
)
from .transfer import Transfer, TransferAll
from .weights import CommitWeights, RevealWeights, SetWeights, normalize

__all__ = [
    "Intent",
    "Plan",
    "Policy",
    "REGISTRY",
    "register",
    "build",
    "list_tools",
    "AddStake",
    "AddStakeLimit",
    "RemoveStake",
    "RemoveStakeLimit",
    "MoveStake",
    "SwapStake",
    "TransferStake",
    "UnstakeAll",
    "UnstakeAllAlpha",
    "SetAutoStake",
    "Transfer",
    "TransferAll",
    "BurnedRegister",
    "ClaimRoot",
    "RegisterSubnet",
    "RootRegister",
    "SetRootClaimType",
    "StartCall",
    "SwapHotkey",
    "SetChildren",
    "SetChildkeyTake",
    "IncreaseTake",
    "DecreaseTake",
    "SetTake",
    "ServeAxon",
    "ServeAxonTls",
    "ServePrometheus",
    "SetWeights",
    "CommitWeights",
    "RevealWeights",
    "AddLiquidity",
    "ModifyLiquidity",
    "RemoveLiquidity",
    "LockStake",
    "SetPerpetualLock",
    "MoveLock",
    "TrimSubnet",
    "StakeBurn",
    "SenateVote",
    "SetMechanismCount",
    "SetMechanismEmissionSplit",
    "UpdateSymbol",
    "CreatePureProxy",
    "KillPureProxy",
    "ExecuteProxyAnnounced",
    "ResetAxon",
    "AddProxy",
    "RemoveProxy",
    "RemoveProxies",
    "PROXY_TYPES",
    "Batch",
    "AnnounceColdkeySwap",
    "SwapColdkeyAnnounced",
    "ClearColdkeySwapAnnouncement",
    "DisputeColdkeySwap",
    "SetIdentity",
    "SetSubnetIdentity",
    "RegisterLeasedNetwork",
    "TerminateLease",
    "AssociateHotkey",
    "AssociateEvmKey",
    "MultisigThreshold1",
    "MultisigExecute",
    "MultisigApprove",
    "MultisigCancel",
    "SetHyperparameter",
    "OWNER_HYPERPARAMETERS",
    "CreateCrowdloan",
    "ContributeCrowdloan",
    "FinalizeCrowdloan",
    "RefundCrowdloan",
    "DissolveCrowdloan",
    "WithdrawCrowdloan",
    "UpdateCrowdloanCap",
    "UpdateCrowdloanEnd",
    "UpdateCrowdloanMinContribution",
    "SetCrowdloanMaxContribution",
    "normalize",
]
