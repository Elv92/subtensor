# subtensor

A lean Python SDK and CLI for the Bittensor chain. One install gives you both a
library (`import subtensor`) and a command line (`subtensor`).

The design goal is a thin, unopinionated wrapper: easy, safe, and fast to do the
core chain operations, with nothing hidden. It does **not** implement the neuron
networking layer (axon/dendrite/synapse) — it is the layer that talks to the
chain.

## Why it's built this way

Almost everything is a projection of the chain's own runtime metadata:

- The **generated layer** (`subtensor.storage`, `runtime_api`, `constants`,
  `calls`) is emitted from metadata, so it can't drift from the chain.
- **Reads** (36 of them) and **intents** (58 of them) are the small hand-written
  semantic layer on top — the part metadata can't express (units, safety,
  aggregation).
- The **CLI is generated from those registries**: every read becomes a
  `subtensor query <name>`, every intent becomes a `subtensor tx <name>`. Adding
  an SDK operation adds its command for free, and the two can't diverge.
- A CI gate proves every chain call is either wrapped by an intent or explicitly
  marked raw-only, so nothing is silently forgotten.

## Install

Requires Python 3.10–3.13. Using [uv](https://docs.astral.sh/uv/):

```bash
uv venv && source .venv/bin/activate
uv pip install -e .
```

This installs the `subtensor` command and the `subtensor` Python package.

## CLI

### Networks and configuration

Every command accepts the connection and identity options. Set them per-command,
via environment variables, or persist them once:

```bash
subtensor config set network test
subtensor config set wallet my_coldkey
subtensor config get            # show the whole config
```

Precedence, highest first: **CLI flag > environment variable > config file >
built-in default**. So after the config above, `subtensor query tx-rate-limit`
talks to testnet, but `subtensor -n finney query tx-rate-limit` overrides it for
that one call.

Global options appear on every command's `--help`:

| Option | Env | Meaning |
| --- | --- | --- |
| `--network`, `-n` | `BT_NETWORK` | `finney` / `test` / `local`, or a `ws://` endpoint |
| `--wallet`, `-w` | `BT_WALLET` | coldkey wallet name |
| `--wallet-hotkey`, `-H` | `BT_WALLET_HOTKEY` | hotkey name within the wallet |
| `--wallet-path` | `BT_WALLET_PATH` | wallet directory |
| `--json` | | machine-readable JSON output |
| `--yes`, `-y` | | skip confirmation prompts |
| `--dry-run` | | preview a mutation without submitting |
| `--quiet`, `-q` | | suppress informational output |

### Shell completion

Ready-made completion scripts ship in `completions/` (and are installed into the
standard system locations — `share/bash-completion/completions`,
`share/zsh/site-functions`, `share/fish/vendor_completions.d`). On most system or
Homebrew-style installs shells pick them up automatically, so there's nothing to
run.

If your shell doesn't auto-load them (e.g. a venv/`uv` install), source the
script once from your rc file:

```bash
# bash (~/.bashrc)
source /path/to/completions/subtensor.bash
# zsh (~/.zshrc) — or drop `_subtensor` on your $fpath
source /path/to/completions/_subtensor
# fish — copy into a dir fish auto-loads
cp /path/to/completions/subtensor.fish ~/.config/fish/completions/
```

`subtensor --install-completion` still works if you'd rather have it edit your
rc file for you.

### Wallets

```bash
subtensor wallet create -w my_coldkey
subtensor wallet list
subtensor wallet regen-coldkey -w my_coldkey     # prompts for the mnemonic securely
subtensor wallet sign --message "hello" --use-hotkey -w my_coldkey
subtensor wallet verify --message "hello" --signature 0x... --ss58 5F...
```

### Reading state

```bash
subtensor balance show 5F...coldkey
subtensor subnets list
subtensor subnets show 1
subtensor stake show --hotkey 5F...validator --netuid 1

# Generated read commands (one per SDK read):
subtensor query metagraph --netuid 1
subtensor query delegate-take --hotkey 5F...
subtensor query crowdloan --crowdloan-id 0
subtensor query --help          # full list
```

### Submitting transactions

Every intent is a `subtensor tx <name>`; run `subtensor tx --help` for the list.

```bash
# Preview first (fee, effects, policy) — nothing is submitted:
subtensor tx add-stake --hotkey 5F...validator --netuid 1 --amount-tao 10 --dry-run

# Submit (prompts to confirm unless --yes):
subtensor tx add-stake --hotkey 5F...validator --netuid 1 --amount-tao 10 -w my_coldkey
subtensor tx transfer --dest 5F...dest --amount-tao 1.5 -w my_coldkey --yes
```

### Address arguments accept local names

Any address option (`--dest`, `--hotkey`, `--coldkey`, and the `balance show` address) takes three forms:

- a raw ss58 address;
- a **local key name** — hotkey options take `HOTKEY` or `WALLET/HOTKEY`; coldkey
  options take a wallet name;
- **omitted**, in which case `--hotkey` / `--coldkey` fall back to your
  configured wallet's key. Destination-style options never default.

```bash
subtensor query hotkey-owner --hotkey my_coldkey/my_hotkey
subtensor balance show my_coldkey      # resolves the wallet's coldkey
```

## SDK

### Reading

```python
import asyncio
import subtensor as sub

async def main():
    async with sub.Client("finney") as client:
        # Typed conveniences
        bal = await client.balances.get("5F...coldkey")
        subnets = await client.subnets.all()
        neurons = await client.neurons.all(netuid=1)

        # Named reads (same set the CLI `query` group exposes)
        mg = await client.read("metagraph", netuid=1)
        take = await client.read("delegate_take", hotkey_ss58="5F...")

        # Generic accessors over the generated descriptors — anything on chain
        tempo = await client.query(sub.storage.SubtensorModule.Tempo, [1])
        ed = await client.constant(sub.constants.Balances.ExistentialDeposit)

asyncio.run(main())
```

There is a synchronous facade too:

```python
client = sub.SyncClient("finney")
print(client.balances.get("5F...coldkey"))
client.close()
```

### Writing: intents, plan, execute

A mutation is an **intent** — a serializable dataclass. `plan` previews it
(fee, effects, warnings, policy) without submitting; `execute` signs and submits
through a single policy-gated choke point.

```python
from bittensor_wallet import Wallet
wallet = Wallet(name="my_coldkey", hotkey="my_hotkey")

async with sub.Client("finney") as client:
    intent = sub.AddStake(hotkey_ss58="5F...validator", netuid=1, amount_tao=10)

    plan = await client.plan(intent, wallet)
    print(plan.fee, plan.effects, plan.ok)

    result = await client.execute(intent, wallet)
    print(result.success, result.block_hash)
```

Build intents by name (handy for agents and tools):

```python
await client.execute_tool("transfer", {"dest_ss58": "5F...", "amount_tao": 1.0}, wallet)
```

### Safety: Policy

Attach a `Policy` to bound what any mutation may do; violations raise
`PolicyError` at execute time (and show up in `plan`).

```python
policy = sub.Policy(max_spend_tao=5.0, allowed_netuids=[1, 2])
async with sub.Client("finney", policy=policy) as client:
    ...
```

### Typed money

`Balance` is unit-tagged (TAO vs. a subnet's alpha) and refuses to mix units, so
you can't accidentally pass alpha where TAO is expected. Use strings/`Decimal`
for exact large amounts.

```python
sub.Balance.from_tao("10000000.123456789")   # exact
sub.tao(1.5); sub.rao(1_500_000_000)
```

### Typed errors

Failures come back as `ExtrinsicResult` with a machine-readable `ErrorCode` and a
remediation hint, derived from the exact chain error name:

```python
result = await client.execute(sub.BurnedRegister(netuid=999), wallet)
if not result.success:
    print(result.error.code, result.error.remediation)  # e.g. subnet_not_exists
```

## Advanced submission modes

These compose with any intent:

- **Proxy** — sign as a registered proxy so the real coldkey stays offline:

  ```python
  await client.execute(intent, delegate_wallet, proxy_for="5F...real_coldkey")
  ```
  On the CLI: `--proxy-for <ss58|wallet>` on any `subtensor tx` command. Manage
  delegations with the `add-proxy` / `remove-proxy` intents and the `proxies` read.

- **Atomic batch** — several intents in one all-or-nothing extrinsic:

  ```python
  await client.execute(sub.Batch(intents=[
      {"op": "transfer", "dest_ss58": "5F...", "amount_tao": 1.0},
      {"op": "add_stake", "hotkey_ss58": "5F...", "netuid": 1, "amount_tao": 2.0},
  ]), wallet)
  ```

- **MEV-shielded** — encrypt the call so the mempool can't front-run it (a
  mainnet feature; needs validator-side reveal):

  ```python
  await client.submit_shielded(sub.Transfer(dest_ss58="5F...", amount_tao=1.0), wallet)
  ```

## Escape hatch: raw calls

Every chain call the metadata exposes is available under `subtensor.calls`, even
the ones no intent wraps. Submit one directly (an active `Policy` refuses this
unless it sets `allow_raw_calls=True`):

```python
call = sub.calls.Commitments.set_commitment(netuid=1, info={...})
await client.submit_call(call, wallet, signer="hotkey")
```

## For agents

The full catalog of executable operations and their JSON schemas is available
programmatically and on the CLI, so an agent can discover and call everything
without hard-coded knowledge:

```bash
subtensor tools        # machine-readable JSON of every intent + params
```

```python
sub.intents.list_tools()
```

Combined with `--json` on every command, `--dry-run` to preview, and
`Policy` to bound spend/netuids, the CLI is safe for automated use (it refuses to
hang on a prompt: a non-interactive session without `--yes` is declined, not
blocked).

## What's covered

The intent layer wraps every user-facing state transition across the runtime —
staking, transfers, registration, weights, children/take, proxies, multisig,
crowdloans, coldkey swap, identity, leasing, auto-staking, serving, and
subnet-owner hyperparameters. Calls left as raw-only are deprecated, root/admin
only, or off-chain-signed; each is recorded with a reason and reachable through
`submit_call`.

## Development

The generated layer is emitted from a node's metadata and committed. Regenerate
and check it against a running node:

```bash
python -m codegen <ws-endpoint>          # regenerate subtensor/_generated
python -m codegen.check --drift <ws>     # committed files match chain metadata
python -m codegen.check --coverage       # every chain call has a deliberate status
python -m codegen.check --names          # every classified error name still exists
```

End-to-end verification against a local dev node asserts real on-chain state
changes for every operation:

```bash
python scripts/verify.py [ws-endpoint]   # default ws://127.0.0.1:9944
```
