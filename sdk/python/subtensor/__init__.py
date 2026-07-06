"""Bittensor SDK: a lean, unopinionated client for the Bittensor chain.

Quick start:

    import asyncio
    import subtensor as sub

    async def main():
        async with sub.Client("finney") as client:
            bal = await client.balances.get("5F...coldkey")
            print(bal)

    asyncio.run(main())

Synchronous:

    client = sub.SyncClient("finney")
    print(client.balances.get("5F...coldkey"))
    client.close()
"""

from . import intents, wallets
from ._generated import calls, constants, runtime_apis as runtime_api, storage
from .balance import Balance, UnitMismatchError, rao, tao
from .client import BlockHeader, Client
from .intents import REGISTRY as _INTENT_REGISTRY
from .intents import Intent, Plan, Policy
from .multisig import Multisig
from .neurons import Neuron
from .result import (
    BittensorError,
    ChainError,
    ConnectionNotReady,
    ErrorCode,
    ExtrinsicResult,
    PolicyError,
)
from .signing import Signer, WalletSigner, public_view, resolve_signer
from .extension import (
    BridgeClient,
    BridgeError,
    BridgeServer,
    ExtensionAccount,
    ExtensionSigner,
    connect_extension_signer,
    ensure_bridge,
    run_bridge,
    stop_bridge_daemon,
)
from .wallets import (
    CRYPTO_ED25519,
    CRYPTO_SR25519,
    DEFAULT_CRYPTO_TYPE,
    format_crypto_type,
    parse_crypto_type,
)
from .snapshot import Snapshot
from .subnets import SubnetInfo
from .sync import SyncClient

# Re-export every registered intent class at the top level, derived from the
# registry so this can never drift from the actual set of intents (the codegen
# coverage gate is the source of truth for which intents exist).
_INTENT_EXPORTS = {cls.__name__: cls for cls in _INTENT_REGISTRY.values()}
globals().update(_INTENT_EXPORTS)

__all__ = [
    "Client",
    "SyncClient",
    "Snapshot",
    "BlockHeader",
    "Neuron",
    "SubnetInfo",
    "Balance",
    "UnitMismatchError",
    "tao",
    "rao",
    "ExtrinsicResult",
    "BittensorError",
    "ChainError",
    "ConnectionNotReady",
    "ErrorCode",
    "PolicyError",
    "wallets",
    # Generated chain vocabulary (descriptors for query/runtime/constant, and
    # raw call builders for the submit_call escape hatch)
    "storage",
    "runtime_api",
    "constants",
    "calls",
    # Intent layer
    "intents",
    "Intent",
    "Plan",
    "Policy",
    "Multisig",
    "Signer",
    "WalletSigner",
    "public_view",
    "resolve_signer",
    "BridgeClient",
    "BridgeError",
    "BridgeServer",
    "ExtensionAccount",
    "ExtensionSigner",
    "connect_extension_signer",
    "ensure_bridge",
    "run_bridge",
    "stop_bridge_daemon",
    "CRYPTO_ED25519",
    "CRYPTO_SR25519",
    "DEFAULT_CRYPTO_TYPE",
    "parse_crypto_type",
    "format_crypto_type",
    *sorted(_INTENT_EXPORTS),
]

__version__ = "0.1.0"
