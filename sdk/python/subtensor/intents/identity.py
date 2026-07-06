"""On-chain identity: human-readable metadata for coldkeys and subnets.

Read back with the ``identity`` / ``subnet_identity`` reads. String fields are
sent as their utf-8 bytes; the chain stores raw ``Vec<u8>``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .._generated import calls
from .base import Intent
from .registry import register


@register
@dataclass
class SetIdentity(Intent):
    """Publish an on-chain identity (name, links, description) for the coldkey."""

    op = "set_identity"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_identity"),)

    name: str
    url: str = ""
    github_repo: str = ""
    image: str = ""
    discord: str = ""
    description: str = ""
    additional: str = ""

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.set_identity(
                name=self.name.encode(),
                url=self.url.encode(),
                github_repo=self.github_repo.encode(),
                image=self.image.encode(),
                discord=self.discord.encode(),
                description=self.description.encode(),
                additional=self.additional.encode(),
            )
        )

    def summary(self) -> str:
        return f"set on-chain identity to {self.name!r}"


@register
@dataclass
class SetSubnetIdentity(Intent):
    """Publish identity metadata for a subnet (signer must be the subnet owner)."""

    op = "set_subnet_identity"
    signer = "coldkey"
    wraps = (("SubtensorModule", "set_subnet_identity"),)

    netuid: int
    subnet_name: str
    github_repo: str = ""
    subnet_contact: str = ""
    subnet_url: str = ""
    discord: str = ""
    description: str = ""
    logo_url: str = ""
    additional: str = ""

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.set_subnet_identity(
                netuid=self.netuid,
                subnet_name=self.subnet_name.encode(),
                github_repo=self.github_repo.encode(),
                subnet_contact=self.subnet_contact.encode(),
                subnet_url=self.subnet_url.encode(),
                discord=self.discord.encode(),
                description=self.description.encode(),
                logo_url=self.logo_url.encode(),
                additional=self.additional.encode(),
            )
        )

    def summary(self) -> str:
        return f"set subnet {self.netuid} identity to {self.subnet_name!r}"
