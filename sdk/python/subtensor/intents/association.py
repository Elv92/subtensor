"""Key association: link a hotkey to a coldkey, or an EVM key to a hotkey."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .._generated import calls
from .base import Intent
from .registry import register


@register
@dataclass
class AssociateHotkey(Intent):
    """Associate a hotkey with the signing coldkey.

    Records on chain that the signing coldkey owns the hotkey, without
    registering it on any subnet or staking anything. Useful when the pairing
    should be visible before the hotkey's first registration (registration and
    staking establish it as a side effect). The chain only associates hotkeys
    that are not already owned, so this cannot take over a hotkey that belongs
    to another coldkey.
    """

    op = "associate_hotkey"
    signer = "coldkey"
    wraps = (("SubtensorModule", "try_associate_hotkey"),)

    hotkey_ss58: Optional[str] = field(
        default=None,
        metadata={"help": "Hotkey to record as owned by the signing coldkey."},
    )

    async def build(self, substrate, wallet: Any):
        hotkey = self.hotkey_ss58 or wallet.hotkey.ss58_address
        return await substrate.compose(calls.SubtensorModule.try_associate_hotkey(hotkey=hotkey))

    def summary(self) -> str:
        return f"associate hotkey {self.hotkey_ss58 or 'the wallet hotkey'} with the coldkey"


@register
@dataclass
class AssociateEvmKey(Intent):
    """Associate an EVM key with a hotkey on a subnet.

    Links an Ethereum-style (H160) address to the signing hotkey on one subnet,
    letting EVM-side activity be attributed to that neuron. Signed by the
    hotkey, and additionally proven by the EVM key itself: ``signature`` must
    be the EVM key's signature over ``keccak_256(hotkey ++
    keccak_256(block_number))`` for the given ``block_number``. Producing that
    signature is up to the caller since it requires the EVM private key; a
    wrong message, block number, or key makes the chain reject the call.
    """

    op = "associate_evm_key"
    signer = "hotkey"
    wraps = (("SubtensorModule", "associate_evm_key"),)

    netuid: int = field(metadata={"help": "Subnet on which the EVM key association is recorded."})
    evm_key: str = field(
        metadata={"help": "EVM address to link to the hotkey, as 0x-prefixed H160 hex."}
    )
    block_number: int = field(
        metadata={
            "help": "Block number the signature was produced for; part of the signed message."
        }
    )
    signature: str = field(
        metadata={
            "help": "The EVM key's signature proving ownership, as 0x-prefixed hex. Signs "
            "keccak_256 of the hotkey concatenated with keccak_256 of the block number."
        }
    )

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
