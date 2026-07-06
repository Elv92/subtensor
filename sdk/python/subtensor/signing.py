"""The signing seam: anything that can sign an extrinsic.

The SDK never requires a raw private key — it requires a :class:`Signer`: an
address, a public key, a crypto type, and a ``sign(payload)`` method. The
transport already awaits ``sign`` when it returns a coroutine, so signers that
round-trip to a device or a service (Ledger, OS keychain, remote signing box)
fit the same protocol without the SDK changing.

``bittensor_wallet`` keyfiles are the first backend (:class:`WalletSigner`).
Every SDK API that accepts a ``wallet`` also accepts a ``Signer`` directly:
``resolve_signer`` at the signing choke points wraps a ``Wallet`` and passes
anything already signer-shaped through untouched.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from bittensor_wallet import Wallet

from .wallets import signing_keypair

_ROLES = ("coldkey", "hotkey")


@runtime_checkable
class Signer(Protocol):
    """Anything that can sign an extrinsic payload.

    ``ss58_address`` is the chain account address (ss58 encoding applies to both
    ed25519 and sr25519 keys). ``crypto_type`` selects the signature scheme:
    ``0`` = ed25519, ``1`` = sr25519.

    ``sign`` may be a plain function or a coroutine function — the transport
    awaits the result if needed, so hardware and remote signers can block on
    user approval without holding the event loop hostage.
    """

    @property
    def ss58_address(self) -> str:
        ...

    @property
    def public_key(self) -> bytes:
        ...

    @property
    def crypto_type(self) -> int:
        ...

    def sign(self, payload: bytes) -> bytes:
        ...


class WalletSigner:
    """A :class:`Signer` backed by a ``bittensor_wallet`` keyfile.

    Public attributes (address, public key) come from the plaintext pub files,
    so building the signer, addressing, and fee estimation never unlock
    anything. The private key is unlocked lazily on the first ``sign`` via the
    password resolution chain (see ``wallets.resolve_wallet_password``) and
    kept for the signer's lifetime — one unlock per process, not per
    signature.
    """

    def __init__(
        self,
        wallet: Wallet,
        role: str = "coldkey",
        *,
        password: Optional[str] = None,
        password_file: Optional[str] = None,
        macos_prompt: bool = False,
        keychain: bool = False,
    ):
        if role not in _ROLES:
            raise ValueError(f"role must be one of {_ROLES}, got {role!r}")
        self._wallet = wallet
        self._role = role
        self._password = password
        self._password_file = password_file
        self._macos_prompt = macos_prompt
        self._keychain = keychain
        self._keypair: Any = None

    def _public(self) -> Any:
        """A public-only keypair — never triggers an unlock."""
        if self._keypair is not None:
            return self._keypair
        # Hotkeys are stored unencrypted; the coldkey pub file is always plaintext.
        return self._wallet.coldkeypub if self._role == "coldkey" else self._wallet.hotkey

    def _unlock(self) -> Any:
        if self._keypair is None:
            self._keypair = signing_keypair(
                self._wallet,
                self._role,
                password=self._password,
                password_file=self._password_file,
                macos_prompt=self._macos_prompt,
                keychain=self._keychain,
            )
        return self._keypair

    @property
    def ss58_address(self) -> str:
        return self._public().ss58_address

    @property
    def public_key(self) -> bytes:
        return self._public().public_key

    @property
    def crypto_type(self) -> int:
        return self._public().crypto_type

    @property
    def ss58_format(self) -> int:
        return self._public().ss58_format

    def sign(self, payload: bytes) -> bytes:
        return self._unlock().sign(payload)

    def __repr__(self) -> str:
        state = "unlocked" if self._keypair is not None else "locked"
        return f"WalletSigner({self._wallet.name!r}, role={self._role!r}, {state})"


def resolve_signer(
    wallet: Any,
    role: str = "coldkey",
    *,
    password: Optional[str] = None,
    password_file: Optional[str] = None,
    macos_prompt: bool = False,
    keychain: bool = False,
) -> Any:
    """The signer for ``wallet``: a ``Wallet`` is wrapped, a ``Signer`` passes through.

    This is the single seam every signing path goes through. Passing a raw
    ``Keypair`` also works — it already satisfies the protocol.
    """
    if isinstance(wallet, Wallet):
        return WalletSigner(
            wallet,
            role,
            password=password,
            password_file=password_file,
            macos_prompt=macos_prompt,
            keychain=keychain,
        )
    if isinstance(wallet, Signer):
        return wallet
    if getattr(wallet, "uses_extension_signing", False):
        return wallet
    raise TypeError(
        f"cannot sign with {type(wallet).__name__}: expected a bittensor_wallet.Wallet "
        "or an object implementing subtensor.Signer"
    )


def public_view(wallet: Any, role: str = "coldkey") -> Any:
    """An address/public-key view for fee and weight estimation.

    Never unlocks a private key: a ``Wallet`` yields its pub-file keypair, a
    ``Signer`` already exposes its public parts without unlocking.
    """
    if isinstance(wallet, Wallet):
        return wallet.coldkeypub if role == "coldkey" else wallet.hotkey
    return wallet
