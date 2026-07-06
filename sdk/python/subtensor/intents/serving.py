"""Publishing a neuron's endpoint on-chain (axon, TLS axon, prometheus).

This publishes connection info as chain data only — the SDK does not implement
the neuron networking layer itself.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any

from .._generated import calls
from .base import Intent
from .registry import register


@register
@dataclass
class ServeAxon(Intent):
    """Publish this hotkey's axon endpoint (ip:port) for a subnet."""

    op = "serve_axon"
    signer = "hotkey"
    wraps = (("SubtensorModule", "serve_axon"),)

    netuid: int
    ip: str
    port: int
    protocol: int = 4
    version: int = 1

    async def build(self, substrate, wallet: Any):
        address = ipaddress.ip_address(self.ip)
        return await substrate.compose(
            calls.SubtensorModule.serve_axon(
                netuid=self.netuid,
                version=self.version,
                ip=int(address),
                port=self.port,
                ip_type=address.version,
                protocol=self.protocol,
                placeholder1=0,
                placeholder2=0,
            )
        )

    def summary(self) -> str:
        return f"serve axon {self.ip}:{self.port} on netuid {self.netuid}"


@register
@dataclass
class ServeAxonTls(Intent):
    """Publish this hotkey's axon endpoint with a TLS certificate for a subnet.

    Same as ``serve_axon`` plus ``certificate`` (0x-hex bytes) used for
    inter-neuron TLS communication.
    """

    op = "serve_axon_tls"
    signer = "hotkey"
    wraps = (("SubtensorModule", "serve_axon_tls"),)

    netuid: int
    ip: str
    port: int
    certificate: str  # 0x-hex certificate bytes
    protocol: int = 4
    version: int = 1

    async def build(self, substrate, wallet: Any):
        address = ipaddress.ip_address(self.ip)
        return await substrate.compose(
            calls.SubtensorModule.serve_axon_tls(
                netuid=self.netuid,
                version=self.version,
                ip=int(address),
                port=self.port,
                ip_type=address.version,
                protocol=self.protocol,
                placeholder1=0,
                placeholder2=0,
                certificate=bytes.fromhex(self.certificate.removeprefix("0x")),
            )
        )

    def summary(self) -> str:
        return f"serve TLS axon {self.ip}:{self.port} on netuid {self.netuid}"


@register
@dataclass
class ServePrometheus(Intent):
    """Publish this hotkey's prometheus endpoint (ip:port) for a subnet."""

    op = "serve_prometheus"
    signer = "hotkey"
    wraps = (("SubtensorModule", "serve_prometheus"),)

    netuid: int
    ip: str
    port: int
    version: int = 1

    async def build(self, substrate, wallet: Any):
        address = ipaddress.ip_address(self.ip)
        return await substrate.compose(
            calls.SubtensorModule.serve_prometheus(
                netuid=self.netuid,
                version=self.version,
                ip=int(address),
                port=self.port,
                ip_type=address.version,
            )
        )

    def summary(self) -> str:
        return f"serve prometheus {self.ip}:{self.port} on netuid {self.netuid}"


@register
@dataclass
class ResetAxon(Intent):
    """Reset (stop serving) this hotkey's axon endpoint on a subnet."""

    op = "reset_axon"
    signer = "hotkey"
    wraps = (("SubtensorModule", "serve_axon"),)

    netuid: int

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.serve_axon(
                netuid=self.netuid,
                version=0,
                ip=0,
                port=1,
                ip_type=4,
                protocol=4,
                placeholder1=0,
                placeholder2=0,
            )
        )

    def summary(self) -> str:
        return f"reset axon on netuid {self.netuid}"
