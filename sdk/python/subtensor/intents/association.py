"""Key association: link a hotkey to a coldkey, or an EVM key to a hotkey."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .._generated import calls
from .base import Intent
from .registry import register


@register
@dataclass
class AssociateHotkey(Intent):
    """Associate a hotkey with the signing coldkey."""

    op = "associate_hotkey"
    signer = "coldkey"
    wraps = (("SubtensorModule", "try_associate_hotkey"),)

    hotkey_ss58: Optional[str] = None  # defaults to the wallet's hotkey

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(calls.SubtensorModule.try_associate_hotkey(hotkey=hotkey))

    def summary(self) -> str:
        return f"associate hotkey {self.hotkey_ss58 or 'the wallet hotkey'} with the coldkey"


@register
@dataclass
class AssociateEvmKey(Intent):
    """Associate an EVM key with a hotkey on a subnet (hotkey-signed).

    ``signature`` is the EVM key's signature over
    ``keccak_256(hotkey ++ keccak_256(block_number))`` at ``block_number``; both
    ``evm_key`` (H160) and ``signature`` are 0x-hex. Producing the signature is
    up to the caller (it requires the EVM private key).
    """

    op = "associate_evm_key"
    signer = "hotkey"
    wraps = (("SubtensorModule", "associate_evm_key"),)

    netuid: int
    evm_key: str
    block_number: int
    signature: str

    async def build(self, substrate, wallet: Any):
        return await substrate.compose(
            calls.SubtensorModule.associate_evm_key(
                netuid=self.netuid,
                evm_key=self.evm_key,
                block_number=self.block_number,
                signature=bytes.fromhex(self.signature.removeprefix("0x")),
            )
        )

    def summary(self) -> str:
        return f"associate EVM key {self.evm_key} with the hotkey on netuid {self.netuid}"
