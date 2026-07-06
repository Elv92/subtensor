"""Private Substrate transport for the Bittensor SDK.

This package is internal: the SDK's supported surface is `subtensor._substrate.Substrate`
and the domain namespaces on `subtensor.Client`. Nothing here is a public API.
"""

# ruff: noqa: E402

import importlib.metadata


def _check_conflicts():
    """
    Verifies that py-scale-codec (`scalecodec` on PyPI) is not installed, since it
    shares the `scalecodec` namespace with `cyscale`, which this transport requires.
    """
    try:
        _ = importlib.metadata.distribution("scalecodec")
        raise RuntimeError(
            "\n\n"
            "Conflict detected: 'scalecodec' (py-scale-codec) is installed.\n"
            "This conflicts with 'cyscale', which uses the same namespace.\n\n"
            "Please remove it first:\n"
            "    pip uninstall scalecodec cyscale -y\n\n"
            "Then reinstall cyscale:\n"
            "    pip install cyscale --force-reinstall\n"
        )
    except importlib.metadata.PackageNotFoundError:
        pass  # Good — scalecodec is not installed


_check_conflicts()


from .async_substrate import (
    AsyncQueryMapResult,
    AsyncSubstrateInterface,
    AsyncExtrinsicReceipt,
)

__all__ = [
    "AsyncQueryMapResult",
    "AsyncSubstrateInterface",
    "AsyncExtrinsicReceipt",
]
