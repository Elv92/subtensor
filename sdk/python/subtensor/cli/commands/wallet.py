"""`subtensor wallet`: create, regenerate, and list keys."""

from __future__ import annotations

import json
import urllib.request
from typing import Optional

import typer

from ... import macos_password
from ... import config as cfg
from ... import wallets
from ..._generated import storage
from ...intents import (
    AnnounceColdkeySwap,
    AssociateHotkey,
    SetIdentity,
    SwapColdkeyAnnounced,
    SwapHotkey,
    Transfer,
)
from ..context import AppContext, address_cli_name, ctx_of, ss58_param_help
from ..globals import with_globals
from ..helpers import list_coldkeys, wallet_inspect_data, wallet_overview_rows
from .. import multisig_helpers as ms_helpers

app = typer.Typer(no_args_is_help=True, help="Create and manage wallets.")

keychain_app = typer.Typer(
    no_args_is_help=True, help="Store coldkey passwords in the macOS Keychain."
)
app.add_typer(keychain_app, name="keychain")

_CRYPTO_TYPE_HELP = (
    "Key scheme: ed25519 (0) or sr25519 (1, default). ss58 is the address encoding for both."
)


def _resolve_crypto_type(app_ctx: AppContext, value: str) -> int:
    try:
        return wallets.parse_crypto_type(value)
    except ValueError as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)


def _unlock_options(app_ctx: AppContext) -> dict[str, object]:
    return {
        "password_file": app_ctx.wallet_password_file,
        "macos_prompt": app_ctx.macos_password,
        "keychain": app_ctx.keychain_password,
    }


@app.command()
@with_globals
def create(
    ctx: typer.Context,
    n_words: int = typer.Option(12, "--n-words", help="Mnemonic length."),
    no_password: bool = typer.Option(False, "--no-password", help="Do not encrypt the coldkey."),
    overwrite: bool = typer.Option(False, "--overwrite"),
    crypto_type: str = typer.Option("sr25519", "--crypto-type", help=_CRYPTO_TYPE_HELP),
    hotkey_crypto_type: str = typer.Option(
        "sr25519", "--hotkey-crypto-type", help="Hotkey scheme when creating both keys."
    ),
):
    """Create a new coldkey and hotkey."""
    app_ctx: AppContext = ctx_of(ctx)
    coldkey_crypto = _resolve_crypto_type(app_ctx, crypto_type)
    hotkey_crypto = _resolve_crypto_type(app_ctx, hotkey_crypto_type)
    wallet = wallets.create(
        name=app_ctx.wallet_name,
        hotkey=app_ctx.hotkey_name,
        path=app_ctx.wallet_path,
        n_words=n_words,
        use_password=not no_password,
        overwrite=overwrite,
        coldkey_crypto_type=coldkey_crypto,
        hotkey_crypto_type=hotkey_crypto,
    )
    app_ctx.output.detail(
        "created wallet",
        {
            "coldkey": app_ctx.wallet_name,
            "hotkey": app_ctx.hotkey_name,
            "coldkey_crypto_type": wallets.format_crypto_type(coldkey_crypto),
            "hotkey_crypto_type": wallets.format_crypto_type(hotkey_crypto),
            "coldkey_ss58": wallet.coldkeypub.ss58_address,
            "path": app_ctx.wallet_path,
        },
    )


@app.command("new-coldkey")
@with_globals
def new_coldkey(
    ctx: typer.Context,
    n_words: int = typer.Option(12, "--n-words"),
    no_password: bool = typer.Option(False, "--no-password"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    crypto_type: str = typer.Option("sr25519", "--crypto-type", help=_CRYPTO_TYPE_HELP),
):
    """Create a new coldkey in the configured wallet."""
    app_ctx: AppContext = ctx_of(ctx)
    crypto = _resolve_crypto_type(app_ctx, crypto_type)
    wallet = wallets.new_coldkey(
        name=app_ctx.wallet_name,
        path=app_ctx.wallet_path,
        n_words=n_words,
        use_password=not no_password,
        overwrite=overwrite,
        crypto_type=crypto,
    )
    app_ctx.output.detail(
        "created coldkey",
        {
            "wallet": app_ctx.wallet_name,
            "crypto_type": wallets.format_crypto_type(crypto),
            "ss58": wallet.coldkeypub.ss58_address,
        },
    )


@app.command("new-hotkey")
@with_globals
def new_hotkey(
    ctx: typer.Context,
    n_words: int = typer.Option(12, "--n-words"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    crypto_type: str = typer.Option("sr25519", "--crypto-type", help=_CRYPTO_TYPE_HELP),
):
    """Create a new hotkey in the configured wallet."""
    app_ctx: AppContext = ctx_of(ctx)
    crypto = _resolve_crypto_type(app_ctx, crypto_type)
    wallet = wallets.new_hotkey(
        name=app_ctx.wallet_name,
        hotkey=app_ctx.hotkey_name,
        path=app_ctx.wallet_path,
        n_words=n_words,
        overwrite=overwrite,
        crypto_type=crypto,
    )
    app_ctx.output.detail(
        "created hotkey",
        {
            "wallet": app_ctx.wallet_name,
            "hotkey": app_ctx.hotkey_name,
            "crypto_type": wallets.format_crypto_type(crypto),
            "ss58": wallet.hotkey.ss58_address,
        },
    )


@app.command("regen-coldkey")
@with_globals
def regen_coldkey(
    ctx: typer.Context,
    mnemonic: str = typer.Option(
        None,
        "--mnemonic",
        prompt="Coldkey mnemonic",
        hide_input=True,
        help="Coldkey mnemonic. Prompted for securely if omitted; avoid passing on "
        "the command line (it leaks to shell history and the process list).",
    ),
    no_password: bool = typer.Option(False, "--no-password"),
    overwrite: bool = typer.Option(False, "--overwrite"),
    crypto_type: str = typer.Option("sr25519", "--crypto-type", help=_CRYPTO_TYPE_HELP),
):
    """Regenerate a coldkey from a mnemonic."""
    app_ctx: AppContext = ctx_of(ctx)
    crypto = _resolve_crypto_type(app_ctx, crypto_type)
    wallet = wallets.regen_coldkey(
        mnemonic=mnemonic,
        name=app_ctx.wallet_name,
        path=app_ctx.wallet_path,
        use_password=not no_password,
        overwrite=overwrite,
        crypto_type=crypto,
    )
    app_ctx.output.detail(
        "regenerated coldkey",
        {
            "coldkey": app_ctx.wallet_name,
            "crypto_type": wallets.format_crypto_type(crypto),
            "ss58": wallet.coldkeypub.ss58_address,
            "path": app_ctx.wallet_path,
        },
    )


@app.command("regen-hotkey")
@with_globals
def regen_hotkey(
    ctx: typer.Context,
    mnemonic: str = typer.Option(
        None,
        "--mnemonic",
        prompt="Hotkey mnemonic",
        hide_input=True,
        help="Hotkey mnemonic. Prompted for securely if omitted.",
    ),
    overwrite: bool = typer.Option(False, "--overwrite"),
    crypto_type: str = typer.Option("sr25519", "--crypto-type", help=_CRYPTO_TYPE_HELP),
):
    """Regenerate a hotkey from a mnemonic."""
    app_ctx: AppContext = ctx_of(ctx)
    crypto = _resolve_crypto_type(app_ctx, crypto_type)
    wallet = wallets.regen_hotkey(
        mnemonic=mnemonic,
        name=app_ctx.wallet_name,
        hotkey=app_ctx.hotkey_name,
        path=app_ctx.wallet_path,
        overwrite=overwrite,
        crypto_type=crypto,
    )
    app_ctx.output.detail(
        "regenerated hotkey",
        {
            "coldkey": app_ctx.wallet_name,
            "hotkey": app_ctx.hotkey_name,
            "crypto_type": wallets.format_crypto_type(crypto),
            "ss58": wallet.hotkey.ss58_address,
            "path": app_ctx.wallet_path,
        },
    )


@app.command("regen-coldkeypub")
@with_globals
def regen_coldkey_pub(
    ctx: typer.Context,
    ss58: str = typer.Option(..., "--ss58"),
    public_key: str = typer.Option(..., "--public-key", help="Hex public key."),
    overwrite: bool = typer.Option(False, "--overwrite"),
    crypto_type: str = typer.Option("sr25519", "--crypto-type", help=_CRYPTO_TYPE_HELP),
):
    """Regenerate coldkey public file from ss58 + public key."""
    app_ctx: AppContext = ctx_of(ctx)
    crypto = _resolve_crypto_type(app_ctx, crypto_type)
    wallets.regen_coldkey_pub(
        ss58=ss58,
        public_key_hex=public_key,
        name=app_ctx.wallet_name,
        path=app_ctx.wallet_path,
        overwrite=overwrite,
        crypto_type=crypto,
    )
    app_ctx.output.detail(
        "regenerated coldkeypub",
        {"ss58": ss58, "crypto_type": wallets.format_crypto_type(crypto)},
    )


@app.command("regen-hotkeypub")
@with_globals
def regen_hotkey_pub(
    ctx: typer.Context,
    ss58: str = typer.Option(..., "--ss58"),
    public_key: str = typer.Option(..., "--public-key", help="Hex public key."),
    overwrite: bool = typer.Option(False, "--overwrite"),
    crypto_type: str = typer.Option("sr25519", "--crypto-type", help=_CRYPTO_TYPE_HELP),
):
    """Regenerate hotkey public file from ss58 + public key."""
    app_ctx: AppContext = ctx_of(ctx)
    crypto = _resolve_crypto_type(app_ctx, crypto_type)
    wallets.regen_hotkey_pub(
        ss58=ss58,
        public_key_hex=public_key,
        name=app_ctx.wallet_name,
        hotkey=app_ctx.hotkey_name,
        path=app_ctx.wallet_path,
        overwrite=overwrite,
        crypto_type=crypto,
    )
    app_ctx.output.detail(
        "regenerated hotkeypub",
        {"ss58": ss58, "crypto_type": wallets.format_crypto_type(crypto)},
    )


@app.command()
@with_globals
def sign(
    ctx: typer.Context,
    message: str = typer.Option(..., "--message", help="Message text to sign (utf-8)."),
    use_hotkey: bool = typer.Option(
        False, "--use-hotkey", help="Sign with the hotkey instead of the coldkey."
    ),
):
    """Sign a message with the wallet's coldkey (or hotkey)."""
    app_ctx: AppContext = ctx_of(ctx)
    signed = wallets.sign_message(
        message,
        name=app_ctx.wallet_name,
        hotkey=app_ctx.hotkey_name,
        path=app_ctx.wallet_path,
        use="hotkey" if use_hotkey else "coldkey",
        **_unlock_options(app_ctx),
    )
    app_ctx.output.detail("signed", signed)


@app.command()
@with_globals
def verify(
    ctx: typer.Context,
    message: str = typer.Option(..., "--message", help="The exact message that was signed."),
    signature: str = typer.Option(..., "--signature", help="0x-hex signature."),
    ss58: str = typer.Option(..., "--ss58", help="Address the message was signed with."),
):
    """Verify a message signature against an address."""
    app_ctx: AppContext = ctx_of(ctx)
    try:
        ok = wallets.verify_message(message, signature, ss58)
    except (ValueError, TypeError) as error:
        app_ctx.output.error(f"invalid signature or address: {error}")
        raise typer.Exit(1)
    app_ctx.output.detail(None, {"valid": ok, "ss58": ss58})
    if not ok:
        raise typer.Exit(1)


@app.command()
@with_globals
def encrypt(
    ctx: typer.Context,
    message: str = typer.Option(..., "--message"),
    recipient: str = typer.Option(..., "--recipient", help="Recipient ss58 address."),
):
    """Encrypt a message for a recipient (ED25519)."""
    app_ctx: AppContext = ctx_of(ctx)
    result = wallets.encrypt_message(message, recipient)
    app_ctx.output.detail("encrypted", result)


@app.command()
@with_globals
def decrypt(
    ctx: typer.Context,
    ciphertext: str = typer.Option(..., "--ciphertext", help="0x-hex ciphertext."),
    use_hotkey: bool = typer.Option(False, "--use-hotkey"),
):
    """Decrypt a message with the wallet key."""
    app_ctx: AppContext = ctx_of(ctx)
    try:
        plaintext = wallets.decrypt_message(
            ciphertext,
            name=app_ctx.wallet_name,
            hotkey=app_ctx.hotkey_name,
            path=app_ctx.wallet_path,
            use_hotkey=use_hotkey,
            **_unlock_options(app_ctx),
        )
    except Exception as error:
        app_ctx.output.error(f"decryption failed: {error}")
        raise typer.Exit(1)
    app_ctx.output.detail("decrypted", {"message": plaintext})


@app.command("unlock")
@with_globals
def unlock_wallet(ctx: typer.Context):
    """Unlock the configured wallet's coldkey using --macos-password or --keychain-password."""
    app_ctx: AppContext = ctx_of(ctx)
    wallet = app_ctx.wallet()
    if not wallet.coldkey_file.is_encrypted():
        app_ctx.output.detail(
            "unlock",
            {
                "wallet": app_ctx.wallet_name,
                "encrypted": False,
                "ss58": wallet.coldkeypub.ss58_address,
            },
        )
        return
    if not (app_ctx.macos_password or app_ctx.keychain_password or app_ctx.wallet_password_file):
        app_ctx.output.error(
            "pass --macos-password, --keychain-password, or --wallet-password-file to unlock"
        )
        raise typer.Exit(1)
    try:
        keypair = wallets.signing_keypair(wallet, "coldkey", **_unlock_options(app_ctx))
    except (ValueError, OSError) as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)
    app_ctx.output.detail(
        "unlocked",
        {
            "wallet": app_ctx.wallet_name,
            "encrypted": True,
            "ss58": keypair.ss58_address,
        },
    )


@keychain_app.command("save")
@with_globals
def keychain_save(ctx: typer.Context):
    """Save the wallet coldkey password in macOS Keychain (prompts via native dialog)."""
    app_ctx: AppContext = ctx_of(ctx)
    if not macos_password.is_macos():
        app_ctx.output.error("macOS Keychain is only available on darwin")
        raise typer.Exit(1)
    try:
        password = macos_password.prompt_password(
            title=f"Save {app_ctx.wallet_name} coldkey password",
            message=(
                f"Enter the password for wallet {app_ctx.wallet_name!r}. "
                "It will be stored in your macOS Keychain."
            ),
        )
        macos_password.keychain_save(app_ctx.wallet_name, password)
    except (ValueError, OSError) as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)
    app_ctx.output.detail(
        "saved keychain password",
        {
            "wallet": app_ctx.wallet_name,
            "service": macos_password.KEYCHAIN_SERVICE,
            "account": macos_password.keychain_account(app_ctx.wallet_name),
        },
    )


@keychain_app.command("show")
@with_globals
def keychain_show(ctx: typer.Context):
    """Check whether a coldkey password is stored in macOS Keychain."""
    app_ctx: AppContext = ctx_of(ctx)
    if not macos_password.is_macos():
        app_ctx.output.error("macOS Keychain is only available on darwin")
        raise typer.Exit(1)
    stored = macos_password.keychain_load(app_ctx.wallet_name) is not None
    app_ctx.output.detail(
        "keychain",
        {
            "wallet": app_ctx.wallet_name,
            "service": macos_password.KEYCHAIN_SERVICE,
            "stored": stored,
        },
    )


@keychain_app.command("delete")
@with_globals
def keychain_delete(ctx: typer.Context):
    """Remove the wallet coldkey password from macOS Keychain."""
    app_ctx: AppContext = ctx_of(ctx)
    if not macos_password.is_macos():
        app_ctx.output.error("macOS Keychain is only available on darwin")
        raise typer.Exit(1)
    existed = macos_password.keychain_delete(app_ctx.wallet_name)
    app_ctx.output.detail(
        "deleted keychain password",
        {"wallet": app_ctx.wallet_name, "existed": existed},
    )


@app.command("show")
@with_globals
def show_wallet(ctx: typer.Context):
    """Show the configured wallet's public keys and crypto schemes."""
    app_ctx: AppContext = ctx_of(ctx)
    wallet = app_ctx.wallet()
    coldkey_crypto = wallet.coldkeypub.crypto_type
    hotkey_crypto = wallet.hotkey.crypto_type
    app_ctx.output.detail(
        app_ctx.wallet_name,
        {
            "coldkey_ss58": wallet.coldkeypub.ss58_address,
            "coldkey_crypto_type": wallets.format_crypto_type(coldkey_crypto),
            "hotkey": app_ctx.hotkey_name,
            "hotkey_ss58": wallet.hotkey.ss58_address,
            "hotkey_crypto_type": wallets.format_crypto_type(hotkey_crypto),
            "path": app_ctx.wallet_path,
        },
    )


@app.command("list")
@with_globals
def list_wallets(ctx: typer.Context):
    """List wallets on disk and saved multisig wallets."""
    app_ctx: AppContext = ctx_of(ctx)
    coldkeys = wallets.list_wallets_detailed(app_ctx.wallet_path)
    records = [
        {
            "coldkey": ck.name,
            "ss58": ck.ss58,
            "crypto_type": wallets.format_crypto_type(ck.crypto_type),
            "hotkeys": [
                {
                    "name": hk.name,
                    "ss58": hk.ss58,
                    "crypto_type": wallets.format_crypto_type(hk.crypto_type),
                }
                for hk in ck.hotkeys
            ],
        }
        for ck in coldkeys
    ]
    multisig_entries = cfg.load_multisigs()
    multisigs = (
        app_ctx.run(lambda client: ms_helpers.multisig_list_records(client, app_ctx))
        if multisig_entries
        else []
    )
    app_ctx.output.wallet_list(app_ctx.wallet_path, records, multisigs=multisigs)


@app.command("balance")
@with_globals
def wallet_balance(
    ctx: typer.Context,
    address: Optional[str] = typer.Argument(None),
    all_wallets: bool = typer.Option(False, "--all", "-a"),
):
    """Show balance for the configured wallet (supports --all like `subtensor balance show`)."""
    from .balance import show as balance_show

    balance_show(ctx, address=address, all_wallets=all_wallets, sort_by=None)


@app.command("overview")
@with_globals
def wallet_overview(
    ctx: typer.Context,
    all_wallets: bool = typer.Option(False, "--all", "-a"),
    netuid: Optional[int] = typer.Option(None, "--netuid", help="Filter to one subnet."),
):
    """Show wallet stake overview across subnets."""
    app_ctx: AppContext = ctx_of(ctx)
    targets = (
        list_coldkeys(app_ctx.wallet_path)
        if all_wallets
        else [(app_ctx.wallet_name, app_ctx.resolve_address("coldkey_ss58", None))]
    )

    data = app_ctx.run(lambda client: wallet_overview_rows(client, targets, netuid=netuid))
    app_ctx.output.detail("wallet overview", {"wallets": data})


@app.command("history")
@with_globals
def wallet_history(
    ctx: typer.Context,
    coldkey_ss58: Optional[str] = typer.Option(
        None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")
    ),
    limit: int = typer.Option(100, "--limit"),
):
    """Show recent TAO transfers for a coldkey (via SubQuery indexer)."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)
    query = """
    query ($first: Int!, $filter: TransferFilter) {
      transfers(first: $first, filter: $filter, orderBy: BLOCK_NUMBER_DESC) {
        nodes { id from to amount blockNumber extrinsicId }
      }
    }
    """
    payload = json.dumps(
        {
            "query": query,
            "variables": {
                "first": limit,
                "filter": {"or": [{"from": {"equalTo": owner}}, {"to": {"equalTo": owner}}]},
            },
        }
    ).encode()
    request = urllib.request.Request(
        "https://api.subquery.network/sq/TaoStats/bittensor-indexer",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read())
    except OSError as error:
        app_ctx.output.error(f"could not fetch transfer history: {error}")
        raise typer.Exit(1)
    nodes = body.get("data", {}).get("transfers", {}).get("nodes", [])
    rows = [[n.get("blockNumber"), n.get("from"), n.get("to"), n.get("amount")] for n in nodes]
    app_ctx.output.table("transfer history", ["block", "from", "to", "amount"], rows, nodes)


@app.command("transfer")
@with_globals
def wallet_transfer(
    ctx: typer.Context,
    dest_ss58: str = typer.Option(..., address_cli_name("dest_ss58")),
    amount: float = typer.Option(..., "--amount", help="TAO amount."),
):
    """Transfer TAO to another coldkey."""
    app_ctx: AppContext = ctx_of(ctx)
    dest = app_ctx.resolve_address("coldkey_ss58", dest_ss58)
    app_ctx.submit(Transfer(dest_ss58=dest, amount_tao=amount))


@app.command("inspect")
@with_globals
def wallet_inspect(
    ctx: typer.Context,
    coldkey_ss58: Optional[str] = typer.Option(
        None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")
    ),
):
    """Detailed wallet view: balance, stake, delegation, identity."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)

    data = app_ctx.run(
        lambda client: wallet_inspect_data(client, app_ctx.wallet_name, owner)
    )
    app_ctx.output.detail("wallet inspect", data)


@app.command("set-identity")
@with_globals
def set_identity(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name"),
    url: str = typer.Option("", "--url"),
    description: str = typer.Option("", "--description"),
):
    """Set on-chain identity for the wallet coldkey."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(SetIdentity(name=name, url=url, description=description))


@app.command("get-identity")
@with_globals
def get_identity(
    ctx: typer.Context,
    coldkey_ss58: Optional[str] = typer.Option(
        None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")
    ),
):
    """Show on-chain identity for a coldkey."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)
    identity = app_ctx.run(lambda c: c.read("identity", coldkey_ss58=owner))
    app_ctx.output.detail("identity", identity)


@app.command("associate-hotkey")
@with_globals
def associate_hotkey(
    ctx: typer.Context,
    hotkey_ss58: Optional[str] = typer.Option(
        None, address_cli_name("hotkey_ss58"), help=ss58_param_help("hotkey_ss58")
    ),
):
    """Associate a hotkey with the wallet coldkey on chain."""
    app_ctx: AppContext = ctx_of(ctx)
    app_ctx.submit(AssociateHotkey(hotkey_ss58=hotkey_ss58))


@app.command("swap-hotkey")
@with_globals
def swap_hotkey(
    ctx: typer.Context,
    new_hotkey_ss58: str = typer.Option(..., address_cli_name("new_hotkey_ss58")),
    netuid: Optional[int] = typer.Option(None, "--netuid"),
):
    """Swap a registered hotkey for a new one."""
    app_ctx: AppContext = ctx_of(ctx)
    new_hotkey = app_ctx.resolve_address("hotkey_ss58", new_hotkey_ss58)
    app_ctx.submit(SwapHotkey(new_hotkey_ss58=new_hotkey, netuid=netuid))


@app.command("swap-coldkey")
@with_globals
def swap_coldkey(
    ctx: typer.Context,
    new_coldkey_ss58: str = typer.Option(..., address_cli_name("new_coldkey_ss58")),
):
    """Execute an announced coldkey swap."""
    app_ctx: AppContext = ctx_of(ctx)
    new_coldkey = app_ctx.resolve_address("coldkey_ss58", new_coldkey_ss58)
    app_ctx.submit(SwapColdkeyAnnounced(new_coldkey_ss58=new_coldkey))


@app.command("make-multi")
@with_globals
def wallet_make_multi(
    ctx: typer.Context,
    threshold: int = typer.Option(..., "--threshold", min=1),
    signatories: Optional[str] = typer.Option(
        None,
        "--signatories",
        help="Full signer set: ss58, address-book names, or wallet names.",
    ),
    signatory: Optional[list[str]] = typer.Option(
        None, "--signatory", help="One signatory ref; repeat for each member."
    ),
    note: str = typer.Option("", "--note"),
    overwrite: bool = typer.Option(False, "--overwrite"),
):
    """Save a multisig signer set under the -w wallet name for pending and call."""
    app_ctx: AppContext = ctx_of(ctx)
    refs: list[str] = []
    if signatories:
        refs.extend(part.strip() for part in signatories.split(",") if part.strip())
    if signatory:
        refs.extend(signatory)
    refs = list(dict.fromkeys(refs))
    if not refs:
        app_ctx.output.error("pass --signatories or one or more --signatory")
        raise typer.Exit(1)
    try:
        resolved = [app_ctx.resolve_address("coldkey_ss58", ref) for ref in refs]
    except typer.Exit:
        raise
    resolved = list(dict.fromkeys(resolved))
    if threshold > len(resolved):
        app_ctx.output.error(f"threshold {threshold} exceeds {len(resolved)} signatories")
        raise typer.Exit(1)
    if cfg.get_multisig(app_ctx.wallet_name) and not overwrite:
        app_ctx.output.error(
            f"multisig wallet {app_ctx.wallet_name!r} already exists; pass --overwrite"
        )
        raise typer.Exit(1)
    try:
        entry = cfg.add_multisig(
            {
                "name": app_ctx.wallet_name,
                "threshold": threshold,
                "signatories": refs,
                "note": note,
            }
        )
    except ValueError as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)

    async def derive(client):
        ms = await client.multisig(resolved, threshold)
        sudo_key = await client.query(storage.Sudo.Key)
        return ms.address, sudo_key

    address, sudo_key = app_ctx.run(derive)
    coldkey_exists = False
    try:
        wallets.open_wallet(name=app_ctx.wallet_name, path=app_ctx.wallet_path)
        coldkey_exists = True
    except Exception:
        pass
    app_ctx.output.detail(
        "saved multisig wallet",
        {
            "wallet": app_ctx.wallet_name,
            "entry": entry,
            "path": str(cfg.multisigs_path()),
            "multisig_address": address,
            "chain_sudo_key": sudo_key,
            "matches_sudo": address == sudo_key,
            "coldkey_wallet_also_exists": coldkey_exists,
        },
    )


@app.command("pending")
@with_globals
def wallet_pending(
    ctx: typer.Context,
    multisig: Optional[str] = typer.Option(
        None,
        "--multisig",
        help="Named multisig wallet (same name as -w); defaults to -w when saved.",
    ),
    multisig_threshold: Optional[int] = typer.Option(
        None,
        "--multisig-threshold",
        help="Approvals needed before the multisig call executes.",
    ),
    signatories: Optional[str] = typer.Option(
        None,
        "--signatories",
        help="Full signer set: ss58, address-book names, or wallet names (include yourself).",
    ),
    other_signatories: Optional[str] = typer.Option(
        None,
        "--other-signatories",
        help="Other signers only (book names or ss58); your -w wallet coldkey is added.",
    ),
    signer: str = typer.Option(
        "coldkey", "--signer", help="Which wallet key is in the signer set: 'coldkey' or 'hotkey'."
    ),
    call_hash: Optional[str] = typer.Option(
        None,
        "--call-hash",
        help="Show one pending operation by call hash.",
    ),
    call_data: Optional[str] = typer.Option(
        None,
        "--call-data",
        help="Scale-encoded call hex. Use when call details are not in local cache.",
    ),
):
    """List pending multisig operations with approval status and co-signer commands."""
    app_ctx: AppContext = ctx_of(ctx)
    if signer not in ("coldkey", "hotkey"):
        app_ctx.output.error("signer must be 'coldkey' or 'hotkey'")
        raise typer.Exit(1)
    try:
        threshold, signatories_resolved, preset, signatory_refs = ms_helpers.resolve_multisig(
            app_ctx,
            multisig_name=multisig,
            threshold=multisig_threshold,
            signatories=signatories,
            other_signatories=other_signatories,
            signer=signer,
            wallet_default=app_ctx.wallet_name,
        )
    except ValueError as error:
        app_ctx.output.error(str(error))
        raise typer.Exit(1)
    if threshold is None:
        app_ctx.output.error(
            f"no multisig for wallet {app_ctx.wallet_name!r}; "
            "run `subtensor wallet make-multi -w NAME ...` or pass inline multisig flags"
        )
        raise typer.Exit(1)

    label = preset or f"{threshold}-of-{len(signatories_resolved)}"

    async def _load(client):
        ms = await client.multisig(signatories_resolved, threshold)
        return await ms_helpers.list_pending_with_commands(
            client,
            app_ctx,
            ms=ms,
            threshold=threshold,
            signatories=signatories_resolved,
            signatory_refs=signatory_refs,
            preset=preset,
            call_hash_filter=call_hash,
            call_data=call_data,
        )

    records = app_ctx.run(_load)
    app_ctx.output.pending_multisigs(records, title=f"pending multisig ({label})")


@app.command("swap-check")
@with_globals
def swap_check(
    ctx: typer.Context,
    coldkey_ss58: Optional[str] = typer.Option(
        None, address_cli_name("coldkey_ss58"), help=ss58_param_help("coldkey_ss58")
    ),
):
    """Check pending coldkey swap announcement."""
    app_ctx: AppContext = ctx_of(ctx)
    owner = app_ctx.resolve_address("coldkey_ss58", coldkey_ss58)
    announcement = app_ctx.run(lambda c: c.read("coldkey_swap_announcement", coldkey_ss58=owner))
    app_ctx.output.detail("coldkey swap status", announcement or {"status": "none"})


@app.command("announce-coldkey-swap")
@with_globals
def announce_coldkey_swap(
    ctx: typer.Context,
    new_coldkey_ss58: str = typer.Option(..., address_cli_name("new_coldkey_ss58")),
):
    """Announce intent to swap coldkey."""
    app_ctx: AppContext = ctx_of(ctx)
    new_coldkey = app_ctx.resolve_address("coldkey_ss58", new_coldkey_ss58)
    app_ctx.submit(AnnounceColdkeySwap(new_coldkey_ss58=new_coldkey))
