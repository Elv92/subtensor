"""Network presets and chain constants.

This is the single place that knows about networks and chain-wide magic numbers.
Everything else takes an explicit endpoint or a network name resolved here.
"""

import os

SS58_FORMAT = 42
TYPE_REGISTRY: dict = {"types": {"Balance": "u64"}}

TAO_SYMBOL = "\u03c4"  # τ
ALPHA_SYMBOL = "\u03b1"  # α

RAO_PER_TAO = 10**9

# Max value of a u16 weight, used for on-chain weight normalization.
U16_MAX = 65535

BLOCKTIME = 12.0

DEFAULT_ERA_PERIOD = 128

# MEV-shielded extrinsics must use a short-lived era: the inner extrinsic has to
# stay valid only until the block author reveals and executes it.
MEV_SHIELD_ERA_PERIOD = 32

GLOBAL_MAX_SUBNET_COUNT = 4096

NETWORKS = {
    "finney": "wss://entrypoint-finney.opentensor.ai:443",
    "test": "wss://test.finney.opentensor.ai:443",
    "archive": "wss://archive.chain.opentensor.ai:443",
    "local": os.getenv("BT_CHAIN_ENDPOINT") or "ws://127.0.0.1:9944",
}

DEFAULT_NETWORK = "finney"


def resolve_endpoint(network: str) -> tuple[str, str]:
    """Resolve a network name or raw ws(s):// URL into (network_label, endpoint_url).

    A bare ``ws://`` or ``wss://`` string is treated as a direct endpoint.
    """
    if network.startswith("ws://") or network.startswith("wss://"):
        label = _REVERSE_NETWORKS.get(network, network)
        return label, network
    try:
        return network, NETWORKS[network]
    except KeyError:
        raise ValueError(
            f"Unknown network {network!r}. Known networks: {sorted(NETWORKS)}, "
            "or pass a ws:// / wss:// endpoint directly."
        ) from None


_REVERSE_NETWORKS = {url: name for name, url in NETWORKS.items()}
