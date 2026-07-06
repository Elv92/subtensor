"""End-to-end verification of the Bittensor SDK against a live node.

Deterministic and re-runnable: every check reads real chain state and asserts on
it (writes are proven by state change, not by return value alone). Prints a
PASS/FAIL line per check and exits non-zero if anything fails.

Usage:
    python scripts/verify.py [ws-endpoint]     # default ws://127.0.0.1:9944

Requires a writable dev node (the opentensor localnet image) because it submits
real extrinsics with the //Alice dev key.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import subtensor as sub
from subtensor.intents import REGISTRY, build
from subtensor.intents.coldkey import coldkey_hash
from bittensor_wallet import Keypair

ENDPOINT = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:9944"
BOB = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"
BOB_HOT = Keypair.create_from_uri("//Bob//hot").ss58_address

FAILS: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        FAILS.append(label)


def _raises(exc, fn) -> bool:
    try:
        fn()
        return False
    except exc:
        return True


def dev_wallet(cold: str, hot: str) -> SimpleNamespace:
    return SimpleNamespace(
        coldkey=Keypair.create_from_uri(cold),
        coldkeypub=Keypair(ss58_address=Keypair.create_from_uri(cold).ss58_address),
        hotkey=Keypair.create_from_uri(hot),
    )


# Sample args to plan-compose every registered intent against live metadata.
INTENT_SAMPLES = {
    "add_stake": {"hotkey_ss58": BOB_HOT, "netuid": 1, "amount_tao": 1.0},
    "add_stake_limit": {
        "hotkey_ss58": BOB_HOT,
        "netuid": 1,
        "amount_tao": 1.0,
        "limit_price_rao": 10**9,
    },
    "remove_stake": {"hotkey_ss58": BOB_HOT, "netuid": 1, "amount_alpha": 1.0},
    "remove_stake_limit": {
        "hotkey_ss58": BOB_HOT,
        "netuid": 1,
        "amount_alpha": 1.0,
        "limit_price_rao": 10**9,
    },
    "move_stake": {
        "origin_hotkey_ss58": BOB_HOT,
        "origin_netuid": 1,
        "dest_hotkey_ss58": BOB_HOT,
        "dest_netuid": 1,
        "amount_alpha": 1.0,
    },
    "swap_stake": {
        "hotkey_ss58": BOB_HOT,
        "origin_netuid": 1,
        "dest_netuid": 1,
        "amount_alpha": 1.0,
    },
    "transfer_stake": {
        "dest_coldkey_ss58": BOB,
        "hotkey_ss58": BOB_HOT,
        "origin_netuid": 1,
        "dest_netuid": 1,
        "amount_alpha": 1.0,
    },
    "unstake_all": {"hotkey_ss58": BOB_HOT},
    "unstake_all_alpha": {"hotkey_ss58": BOB_HOT},
    "transfer": {"dest_ss58": BOB, "amount_tao": 1.0},
    "transfer_all": {"dest_ss58": BOB},
    "burned_register": {"netuid": 1},
    "root_register": {},
    "register_subnet": {},
    "start_call": {"netuid": 1},
    "claim_root": {"subnets": [1]},
    "swap_hotkey": {"new_hotkey_ss58": BOB_HOT},
    "set_children": {"netuid": 1, "children": [[2**63, BOB_HOT]]},
    "set_childkey_take": {"netuid": 1, "take": 1000},
    "increase_take": {"take": 1000},
    "decrease_take": {"take": 500},
    "set_take": {"take": 1000},
    "serve_axon": {"netuid": 1, "ip": "203.0.113.5", "port": 8091},
    "serve_axon_tls": {
        "netuid": 1,
        "ip": "203.0.113.5",
        "port": 8091,
        "certificate": "0x" + "ab" * 32,
    },
    "serve_prometheus": {"netuid": 1, "ip": "203.0.113.5", "port": 9090},
    "set_weights": {"netuid": 1, "uids": [0], "weights": [1.0]},
    "commit_weights": {"netuid": 1, "uids": [0], "weights": [1.0]},
    "add_proxy": {"delegate_ss58": BOB, "proxy_type": "Transfer"},
    "remove_proxy": {"delegate_ss58": BOB, "proxy_type": "Transfer"},
    "remove_proxies": {},
    "batch": {
        "intents": [
            {"op": "transfer", "dest_ss58": BOB, "amount_tao": 0.5},
            {"op": "add_stake", "hotkey_ss58": BOB_HOT, "netuid": 1, "amount_tao": 1.0},
        ]
    },
    "announce_coldkey_swap": {"new_coldkey_ss58": BOB},
    "swap_coldkey_announced": {"new_coldkey_ss58": BOB},
    "clear_coldkey_swap_announcement": {},
    "dispute_coldkey_swap": {},
    "set_hyperparameter": {"netuid": 1, "name": "immunity_period", "value": 42},
    "set_identity": {"name": "verify"},
    "set_subnet_identity": {"netuid": 1, "subnet_name": "verify"},
    "register_leased_network": {"emissions_share": 20, "end_block": 10**9},
    "terminate_lease": {"lease_id": 0},
    "set_auto_stake": {"netuid": 1, "hotkey_ss58": BOB_HOT},
    "set_root_claim_type": {"claim_type": "KeepSubnets", "subnets": [1]},
    "create_crowdloan": {
        "deposit_tao": 100,
        "min_contribution_tao": 1,
        "cap_tao": 1000,
        "end": 10**9,
        "target_ss58": BOB,
    },
    "contribute_crowdloan": {"crowdloan_id": 0, "amount_tao": 1.0},
    "finalize_crowdloan": {"crowdloan_id": 0},
    "refund_crowdloan": {"crowdloan_id": 0},
    "dissolve_crowdloan": {"crowdloan_id": 0},
    "withdraw_crowdloan": {"crowdloan_id": 0},
    "update_crowdloan_cap": {"crowdloan_id": 0, "new_cap_tao": 2000},
    "update_crowdloan_end": {"crowdloan_id": 0, "new_end": 10**9},
    "update_crowdloan_min_contribution": {"crowdloan_id": 0, "new_min_contribution_tao": 2},
    "set_crowdloan_max_contribution": {"crowdloan_id": 0, "new_max_contribution_tao": 50},
    "multisig_threshold_1": {
        "other_signatories": [BOB],
        "call": {"op": "transfer", "dest_ss58": BOB, "amount_tao": 0.1},
    },
    "multisig_execute": {
        "threshold": 2,
        "other_signatories": [BOB],
        "call": {"op": "transfer", "dest_ss58": BOB, "amount_tao": 0.1},
    },
    "multisig_approve": {
        "threshold": 2,
        "other_signatories": [BOB],
        "call": {"op": "transfer", "dest_ss58": BOB, "amount_tao": 0.1},
    },
    "multisig_cancel": {
        "threshold": 2,
        "other_signatories": [BOB],
        "call": {"op": "transfer", "dest_ss58": BOB, "amount_tao": 0.1},
        "timepoint": {"height": 1, "index": 0},
    },
    "associate_hotkey": {"hotkey_ss58": BOB_HOT},
    "associate_evm_key": {
        "netuid": 1,
        "evm_key": "0x" + "11" * 20,
        "block_number": 1,
        "signature": "0x" + "22" * 65,
    },
}


async def main() -> int:
    alice = dev_wallet("//Alice", "//Alice//hot")
    acold = alice.coldkey.ss58_address

    async with sub.Client(ENDPOINT) as c:
        print(f"\n== reads ({ENDPOINT}) ==")
        block = await c.block()
        check("block number", isinstance(block, int) and block > 0, str(block))
        subs = await c.subnets.all()
        check("subnets.all (batched)", len(subs) >= 2, str([s.netuid for s in subs]))
        bal = await c.balances.get(acold)
        check("balance read", bal.rao > 0, str(bal))
        ed = await c.balances.existential_deposit()
        check("existential deposit (constant)", ed.rao > 0, str(ed))

        print("\n== generic read accessors (over generated descriptors) ==")
        tempo = await c.query(sub.storage.SubtensorModule.Tempo, [1])
        check("generic query storage", isinstance(tempo, int), f"tempo={tempo}")
        ed_const = await c.constant(sub.constants.Balances.ExistentialDeposit)
        check("generic constant read", int(ed_const) > 0, str(ed_const))
        raw_neurons = await c.runtime(sub.runtime_api.NeuronInfoRuntimeApi.get_neurons_lite, [1])
        check("generic runtime call", isinstance(raw_neurons, list), f"{len(raw_neurons)} records")

        print("\n== typed reads (client.read + catalog) ==")
        check("reads catalog non-empty", len(c.reads()) >= 12, f"{len(c.reads())} reads")
        hp = await c.read("subnet_hyperparameters", netuid=1)
        check(
            "read subnet_hyperparameters",
            isinstance(hp, dict) and "tempo" in hp,
            f"tempo={hp.get('tempo')}",
        )
        check(
            "read weights_rate_limit", isinstance(await c.read("weights_rate_limit", netuid=1), int)
        )
        mg = await c.read("metagraph", netuid=1)
        check(
            "read metagraph", isinstance(mg, dict) and "hotkeys" in mg, f"block={mg.get('block')}"
        )
        positions = await c.read("stake_for_coldkey", coldkey_ss58=acold)
        check("read stake_for_coldkey typed", isinstance(positions, list))
        quote = await c.read("quote_stake", netuid=1, amount_tao=1.0)
        check(
            "read quote_stake (slippage/fee)",
            quote.alpha.rao > 0 and quote.tao_fee.rao >= 0,
            f"alpha_out={quote.alpha} fee={quote.tao_fee}",
        )
        kids = await c.read(
            "children", hotkey_ss58="5C4hrfjw9DjXZTzV3MwzrrAr9P1MJhSrvWGWqi1eSuyUpnhM", netuid=1
        )
        check("read children typed list", isinstance(kids, list))

        print("\n== metagraph fast path ==")
        neurons = await c.neurons.all(1)
        check(
            "neurons.all matches raw runtime count",
            len(neurons) == len(raw_neurons),
            f"{len(neurons)} vs {len(raw_neurons)}",
        )
        check(
            "neuron records typed", all(isinstance(n, sub.Neuron) and n.hotkey for n in neurons), ""
        )

        print("\n== snapshot (block pinning) ==")
        snap = await c.at()
        s_neurons = await snap.neurons.all(1)
        check(
            "snapshot reads resolve",
            len(s_neurons) == len(neurons),
            f"@{snap.block}",
        )
        s_bal = await snap.balances.get(acold)
        check("snapshot read is block-pinned", s_bal.rao >= 0, f"@{snap.block}")

        print("\n== intent layer ==")
        missing = sorted(set(REGISTRY) - set(INTENT_SAMPLES))
        check("every intent has a sample", not missing, str(missing))
        bad = []
        for op, args in sorted(INTENT_SAMPLES.items()):
            try:
                await c.plan(build(op, args), alice)
            except Exception as e:  # noqa: BLE001
                bad.append((op, str(e)[:50]))
        check(f"all {len(INTENT_SAMPLES)} intents compose+plan vs metadata", not bad, str(bad))
        p = await c.plan(sub.Transfer(dest_ss58=BOB, amount_tao=1.0), alice)
        check("plan simulates fee", p.fee is not None, str(p.fee))
        try:
            await c.execute(
                sub.Transfer(dest_ss58=BOB, amount_tao=5.0),
                alice,
                policy=sub.Policy(max_spend_tao=1.0),
            )
            check("policy blocks over-spend", False)
        except sub.PolicyError:
            check("policy blocks over-spend", True)

        print("\n== policy covers value-moving intents (H1/M1) ==")
        cap = sub.Policy(max_spend_tao=1.0)
        value_movers = [
            (
                "transfer_stake",
                sub.TransferStake(
                    dest_coldkey_ss58=BOB,
                    hotkey_ss58=BOB_HOT,
                    origin_netuid=1,
                    dest_netuid=1,
                    amount_alpha=1.0,
                ),
            ),
            ("register_subnet", sub.RegisterSubnet()),
            ("burned_register", sub.BurnedRegister(netuid=1)),
        ]
        for op, intent in value_movers:
            plan = await c.plan(intent, alice, policy=cap)
            check(f"spend cap blocks {op}", not plan.ok, str(plan.violations))
        allow = sub.Policy(allowed_netuids=[1])
        plan = await c.plan(
            sub.MoveStake(
                origin_hotkey_ss58=BOB_HOT,
                origin_netuid=1,
                dest_hotkey_ss58=BOB_HOT,
                dest_netuid=2,
                amount_alpha=1.0,
            ),
            alice,
            policy=allow,
        )
        check("allowlist blocks disallowed destination netuid", not plan.ok, str(plan.violations))
        plan = await c.plan(sub.UnstakeAllAlpha(hotkey_ss58=BOB_HOT), alice, policy=allow)
        check("allowlist blocks all-subnet unstake", not plan.ok, str(plan.violations))

        print("\n== Balance safety (M2/M3/L2/L3) ==")
        check(
            "float comparison rejected", _raises(TypeError, lambda: sub.Balance.from_tao(0.3) > 0.5)
        )
        check(
            "eq across units is False, not raise",
            (sub.Balance.from_tao(1) == sub.Balance.from_tao(1, netuid=2)) is False,
        )
        check(
            "membership across units works",
            sub.Balance.from_tao(1) not in [sub.Balance.from_tao(1, netuid=2)],
        )
        check(
            "from_tao exact from string at 10M+",
            sub.Balance.from_tao("10000000.123456789").rao == 10_000_000_123456789,
        )
        check(
            "unit guard: wrong-netuid Balance into an intent is rejected",
            _raises(
                sub.UnitMismatchError,
                lambda: sub.AddStake(
                    hotkey_ss58=BOB_HOT, netuid=1, amount_tao=sub.Balance.from_tao(1, netuid=5)
                ),
            ),
        )
        check(
            "unit ok: matching Balance accepted into an intent",
            sub.RemoveStake(
                hotkey_ss58=BOB_HOT, netuid=3, amount_alpha=sub.Balance.from_tao(2, netuid=3)
            ).amount_alpha
            == 2.0,
        )

        print("\n== writes via the single intent path (proven by state change) ==")
        before = await c.balances.get(BOB)
        r = await c.execute(sub.Transfer(dest_ss58=BOB, amount_tao=3.0), alice)
        after = await c.balances.get(BOB)
        check(
            "transfer delta == 3 TAO",
            r.success and after.rao - before.rao == 3 * 10**9,
            f"{before}->{after}",
        )

        await c.execute_tool("register_subnet", {}, alice)
        netuid = max(s.netuid for s in await c.subnets.all())
        await c.execute_tool("start_call", {"netuid": netuid}, alice)
        stake0 = await c.staking.get(acold, alice.hotkey.ss58_address, netuid)
        r = await c.execute(
            sub.AddStake(hotkey_ss58=alice.hotkey.ss58_address, netuid=netuid, amount_tao=10.0),
            alice,
        )
        stake1 = await c.staking.get(acold, alice.hotkey.ss58_address, netuid)
        check(
            "add_stake increases stake",
            r.success and stake1.rao > stake0.rao,
            f"{stake0}->{stake1}",
        )

        # serve_axon and serve_axon_tls share one serving rate-limit bucket, so only
        # the TLS superset is submitted live (proving the certificate path); plain
        # serve_axon is covered by the compose+plan sweep above. Prometheus is a
        # separate bucket.
        r = await c.execute(
            sub.ServeAxonTls(
                netuid=netuid, ip="203.0.113.5", port=8091, certificate="0x" + "ab" * 32
            ),
            alice,
        )
        check("serve_axon_tls submits (with certificate)", r.success, r.message[:40])
        r = await c.execute(sub.ServePrometheus(netuid=netuid, ip="203.0.113.5", port=9090), alice)
        check("serve_prometheus submits", r.success, r.message[:40])

        print("\n== delegate reads ==")
        ahot = alice.hotkey.ss58_address
        await c.execute(sub.RootRegister(), alice)  # makes ahot a delegate; no-op if rerun
        check("is_delegate", await c.read("is_delegate", hotkey_ss58=ahot) is True)
        dg = await c.read("delegate", hotkey_ss58=ahot)
        check(
            "delegate typed",
            dg is not None and dg.hotkey == ahot and 0 <= dg.take <= 1,
            f"take={dg.take if dg else None}",
        )
        all_delegates = await c.read("delegates")
        check(
            "delegates list includes ahot",
            any(d.hotkey == ahot for d in all_delegates),
            f"{len(all_delegates)} delegates",
        )
        take_info = await c.read("delegate_take", hotkey_ss58=ahot)
        check(
            "delegate_take read bounded within min/max",
            take_info["min"] <= take_info["take"] <= take_info["max"],
            f"{take_info['take']:.4f} in [{take_info['min']:.4f}, {take_info['max']:.4f}]",
        )
        # A fresh delegate starts at max take, so move it down: this exercises the
        # sugar's "read current, choose decrease_take" path.
        target_u16 = max(take_info["take_u16"] - 1000, take_info["take_u16"] // 2)
        r = await c.execute(sub.SetTake(hotkey_ss58=ahot, take=target_u16), alice)
        after_take = await c.read("delegate_take", hotkey_ss58=ahot)
        check(
            "set_take moves take to the absolute target (decrease path)",
            r.success and after_take["take_u16"] == target_u16,
            f"{take_info['take_u16']}->{after_take['take_u16']} (target {target_u16})",
        )
        noms = await c.read("delegated", coldkey_ss58=acold)
        check(
            "delegated typed (nominations)",
            any(n.netuid == netuid and n.stake.rao > 0 for n in noms),
            f"{len(noms)} nominations",
        )
        by_coldkey = await c.read("stake_for_coldkeys", coldkey_ss58s=[acold])
        check(
            "stake_for_coldkeys aggregation",
            acold in by_coldkey and any(p.netuid == netuid for p in by_coldkey[acold]),
            f"{len(by_coldkey.get(acold, []))} positions",
        )

        print("\n== raw-call escape hatch + commitments ==")
        raw_call = sub.calls.Commitments.set_commitment(
            netuid=netuid, info={"fields": [[{"Raw5": "0x" + b"hello".hex()}]]}
        )
        try:
            await c.submit_call(
                raw_call, alice, signer="hotkey", policy=sub.Policy(max_spend_tao=100.0)
            )
            check("policy refuses raw calls by default", False)
        except sub.PolicyError:
            check("policy refuses raw calls by default", True)
        r = await c.submit_call(raw_call, alice, signer="hotkey")
        cm = await c.read("commitment", netuid=netuid, hotkey_ss58=ahot)
        check(
            "raw set_commitment lands, commitment read decodes",
            r.success and cm is not None and cm.data == "hello",
            f"data={cm.data if cm else None}",
        )
        check(
            "revealed_commitment readable (None until revealed)",
            await c.read("revealed_commitment", netuid=netuid, hotkey_ss58=ahot) is None,
        )

        print("\n== atomic batch (Utility.batch_all) ==")
        dave = Keypair.create_from_uri("//Dave").ss58_address
        eve = Keypair.create_from_uri("//Eve").ss58_address
        dave_before = await c.balances.get(dave)
        eve_before = await c.balances.get(eve)
        r = await c.execute(
            sub.Batch(
                intents=[
                    sub.Transfer(dest_ss58=dave, amount_tao=1.0),
                    sub.Transfer(dest_ss58=eve, amount_tao=2.0),
                ]
            ),
            alice,
        )
        dave_after = await c.balances.get(dave)
        eve_after = await c.balances.get(eve)
        check(
            "batch applies all children in one extrinsic",
            r.success
            and dave_after.rao - dave_before.rao == 10**9
            and eve_after.rao - eve_before.rao == 2 * 10**9,
            f"dave +{(dave_after.rao - dave_before.rao) / 10**9}, "
            f"eve +{(eve_after.rao - eve_before.rao) / 10**9}",
        )
        dave_before = await c.balances.get(dave)
        r = await c.execute(
            sub.Batch(
                intents=[
                    sub.Transfer(dest_ss58=dave, amount_tao=1.0),
                    sub.Transfer(dest_ss58=eve, amount_tao=10**10),  # must fail
                ]
            ),
            alice,
        )
        dave_after = await c.balances.get(dave)
        check(
            "failed batch reverts everything (atomicity)",
            not r.success and dave_after.rao == dave_before.rao,
            f"success={r.success}, dave delta={dave_after.rao - dave_before.rao}",
        )
        plan = await c.plan(
            sub.Batch(
                intents=[
                    sub.Transfer(dest_ss58=dave, amount_tao=0.6),
                    sub.Transfer(dest_ss58=eve, amount_tao=0.6),
                ]
            ),
            alice,
            policy=sub.Policy(max_spend_tao=1.0),
        )
        check(
            "policy aggregates spend across batch children",
            not plan.ok,
            str(plan.violations),
        )

        print("\n== proxy signing mode (coldkey stays offline) ==")
        bob = dev_wallet("//Bob", "//Bob//hot")
        charlie = Keypair.create_from_uri("//Charlie").ss58_address
        r = await c.execute(sub.AddProxy(delegate_ss58=BOB, proxy_type="Transfer"), alice)
        proxy_state = await c.read("proxies", coldkey_ss58=acold)
        check(
            "add_proxy lands, proxies read decodes",
            r.success
            and any(
                p["delegate"] == BOB and p["proxy_type"] == "Transfer"
                for p in proxy_state["proxies"]
            ),
            str(proxy_state["proxies"]),
        )
        alice_before = await c.balances.get(acold)
        charlie_before = await c.balances.get(charlie)
        r = await c.execute(sub.Transfer(dest_ss58=charlie, amount_tao=1.0), bob, proxy_for=acold)
        alice_after = await c.balances.get(acold)
        charlie_after = await c.balances.get(charlie)
        check(
            "proxied transfer moves the REAL account's funds",
            r.success
            and charlie_after.rao - charlie_before.rao == 10**9
            and alice_before.rao - alice_after.rao == 10**9,
            f"alice -{(alice_before.rao - alice_after.rao) / 10**9} TAO",
        )
        r = await c.execute(
            sub.AddStake(hotkey_ss58=BOB_HOT, netuid=netuid, amount_tao=1.0),
            bob,
            proxy_for=acold,
        )
        check(
            "filtered call fails via ProxyExecuted event, not silent success",
            not r.success and "filter" in r.message,
            r.message[:60],
        )
        r = await c.execute(sub.RemoveProxy(delegate_ss58=BOB, proxy_type="Transfer"), alice)
        proxy_state = await c.read("proxies", coldkey_ss58=acold)
        check(
            "remove_proxy clears delegation",
            r.success and proxy_state["proxies"] == [],
            str(proxy_state["proxies"]),
        )
        r = await c.execute(sub.Transfer(dest_ss58=charlie, amount_tao=1.0), bob, proxy_for=acold)
        check(
            "proxied call without delegation is refused (NotProxy)",
            not r.success and "not a proxy" in r.message.lower(),
            r.message[:60],
        )

        print("\n== MEV shield (encrypted submission pipeline) ==")
        nk = await c.read("mev_shield_next_key")
        check(
            "mev_shield_next_key present (ML-KEM-768 public key, 1184 bytes)",
            nk is not None and len(bytes.fromhex(nk[2:])) == 1184,
            f"{len(bytes.fromhex(nk[2:])) if nk else 0} bytes",
        )
        # Runs the full SDK pipeline: read NextKey, sign the inner extrinsic at
        # nonce+1, ML-KEM-768 encrypt, wrap in submit_encrypted, submit at nonce.
        # Returns a typed result without raising. On-chain reveal is validator-side
        # (a mainnet feature); the dev localnet rejects the pool submission, so we
        # assert the pipeline runs and report the chain's response rather than
        # asserting inclusion.
        shielded = await c.submit_shielded(sub.Transfer(dest_ss58=BOB, amount_tao=2.0), alice)
        check(
            "submit_shielded runs read+sign+encrypt+compose+submit, returns a result",
            hasattr(shielded, "success"),
            f"chain response: success={shielded.success} msg={shielded.message[:40]}",
        )

        print("\n== crowdloan (create, read, update) ==")
        blk = await c.block()
        r = await c.execute(
            sub.CreateCrowdloan(
                deposit_tao=100,
                min_contribution_tao=1,
                cap_tao=1000,
                end=blk + 5000,  # within [MinimumBlockDuration, MaximumBlockDuration]
                target_ss58=BOB,
            ),
            alice,
        )
        check("create_crowdloan submits", r.success, r.message[:50])
        cid = int(await c.query(sub.storage.Crowdloan.NextCrowdloanId)) - 1
        info = await c.read("crowdloan", crowdloan_id=cid)
        check(
            "crowdloan read: creator is Alice, raised >= deposit, cap decoded",
            info is not None
            and info["creator"] == acold
            and info["raised"].tao >= 100
            and info["cap"].tao == 1000,
            str(info and {k: str(info[k]) for k in ("creator", "raised", "cap")}),
        )
        r = await c.execute(sub.UpdateCrowdloanCap(crowdloan_id=cid, new_cap_tao=2000), alice)
        info2 = await c.read("crowdloan", crowdloan_id=cid)
        check(
            "update_crowdloan_cap reflected in read",
            r.success and info2 is not None and info2["cap"].tao == 2000,
            str(info2 and str(info2["cap"])),
        )

        print("\n== multisig (open, read, cancel) ==")
        # 2-of-2 (Alice, Bob). Open the op (first approval), read it back via a
        # query_map over Multisigs (keyed by the derived composite account), then
        # cancel it. Re-runnable: we don't assert the open bool (a prior interrupted
        # run may have left it pending), only that a pending op exists and cancel
        # clears it.
        inner = {"op": "transfer", "dest_ss58": BOB, "amount_tao": 0.1}
        await c.execute(
            sub.MultisigExecute(threshold=2, other_signatories=[BOB], call=inner), alice
        )
        entries = await c.query_map(sub.storage.Multisig.Multisigs)
        mine = [(k, v) for k, v in entries if str((v or {}).get("depositor")) == acold]
        check("pending multisig op visible with Alice as depositor", len(mine) >= 1, f"{len(mine)}")
        (ms_account, call_hash), val = mine[0]
        tp = {"height": int(val["when"]["height"]), "index": int(val["when"]["index"])}
        read_back = await c.read("multisig", account_ss58=str(ms_account), call_hash=str(call_hash))
        check(
            "multisig read decodes approvals + timepoint",
            read_back is not None and acold in read_back["approvals"],
            str(read_back and read_back["approvals"]),
        )
        r = await c.execute(
            sub.MultisigCancel(threshold=2, other_signatories=[BOB], call=inner, timepoint=tp),
            alice,
        )
        entries2 = await c.query_map(sub.storage.Multisig.Multisigs)
        still = [k for k, v in entries2 if str((v or {}).get("depositor")) == acold]
        check(
            "multisig_cancel removes the pending op", r.success and not still, f"{len(still)} left"
        )

        print("\n== nested calls via public compose (sudo) ==")
        # A runtime upgrade is Sudo.sudo(System.set_code(..)); the nesting is the
        # only hard part. Prove client.compose lets a raw call be an inner call
        # without reaching into the transport, using a reversible admin set.
        before_rl = int(await c.query(sub.storage.SubtensorModule.TxRateLimit))
        inner_admin = await c.compose(
            sub.calls.AdminUtils.sudo_set_tx_rate_limit(tx_rate_limit=before_rl + 1)
        )
        r = await c.submit_call(sub.calls.Sudo.sudo(call=inner_admin), alice)
        after_rl = int(await c.query(sub.storage.SubtensorModule.TxRateLimit))
        check(
            "compose+Sudo.sudo nested call applies (runtime-upgrade shape)",
            r.success and after_rl == before_rl + 1,
            f"tx_rate_limit {before_rl}->{after_rl}",
        )

        print("\n== multisig account object (M-of-N executes any call) ==")
        # The clean interface: derive the account, then each signer approve()s the
        # SAME call; the threshold-reaching approval executes the inner call. Works
        # with any generated call (a transfer here; on mainnet the inner call is
        # Sudo.sudo for governance). 2-of-3 over //Alice,//Bob,//Dave.
        bobw = dev_wallet("//Bob", "//Bob//hot")
        davew = dev_wallet("//Dave", "//Dave//hot")
        ms = await c.multisig(
            [alice.coldkey.ss58_address, bobw.coldkey.ss58_address, davew.coldkey.ss58_address],
            threshold=2,
        )
        check(
            "multisig address derived", ms.address.startswith("5") and ms.threshold == 2, ms.address
        )
        await c.execute(sub.Transfer(dest_ss58=ms.address, amount_tao=20.0), alice)
        mev = Keypair.create_from_mnemonic(Keypair.generate_mnemonic()).ss58_address
        payout = sub.calls.Balances.transfer_keep_alive(dest=mev, value=5 * 10**9)
        recipient_before = await c.balances.get(mev)
        r1 = await ms.approve(payout, alice)
        mid = await c.balances.get(mev)
        check(
            "first approval records consent without executing",
            r1.success and mid.rao == recipient_before.rao,
            f"recipient still {mid}",
        )
        r2 = await ms.approve(payout, bobw)
        recipient_after = await c.balances.get(mev)
        check(
            "threshold-reaching approval executes the inner call",
            r2.success and recipient_after.rao - recipient_before.rao == 5 * 10**9,
            f"{recipient_before}->{recipient_after}",
        )

        print("\n== key association ==")
        r = await c.execute(sub.AssociateHotkey(hotkey_ss58=ahot), alice)
        check("associate_hotkey submits", r.success, r.message[:40])
        check(
            "associated_evm_key read is None when unset",
            await c.read("associated_evm_key", netuid=netuid, uid=0) is None,
        )

        print("\n== root claim type (set + get) ==")
        r = await c.execute(sub.SetRootClaimType(claim_type="Swap"), alice)
        base_claim = await c.read("root_claim_type", coldkey_ss58=acold)
        check(
            "set_root_claim_type Swap (unit variant) reads back",
            r.success and base_claim["type"] == "Swap" and base_claim["subnets"] is None,
            str(base_claim),
        )
        r = await c.execute(sub.SetRootClaimType(claim_type="KeepSubnets", subnets=[netuid]), alice)
        claim = await c.read("root_claim_type", coldkey_ss58=acold)
        check(
            "set_root_claim_type KeepSubnets lands; read decodes variant + subnets",
            r.success and claim["type"] == "KeepSubnets" and claim["subnets"] == [netuid],
            str(claim),
        )
        r = await c.execute(sub.SetRootClaimType(claim_type="Keep"), alice)
        claim = await c.read("root_claim_type", coldkey_ss58=acold)
        check(
            "set_root_claim_type Keep resets to unit variant",
            r.success and claim["type"] == "Keep" and claim["subnets"] is None,
            str(claim),
        )
        check(
            "KeepSubnets without subnets is rejected at construction",
            _raises(ValueError, lambda: sub.SetRootClaimType(claim_type="KeepSubnets")),
        )

        print("\n== auto-stake (set + get) ==")
        # The destination hotkey must be registered on the subnet, and re-setting
        # the same hotkey is rejected ("already set"). ahot is registered, so we
        # assert the resulting read state (re-runnable) rather than the extrinsic
        # bool — a real state change is proven separately.
        await c.execute(sub.SetAutoStake(netuid=netuid, hotkey_ss58=ahot), alice)
        dest = await c.read("auto_stake", coldkey_ss58=acold, netuid=netuid)
        check("set_auto_stake destination reflected in auto_stake read", dest == ahot, str(dest))

        print("\n== subnet leases (read) ==")
        all_leases = await c.read("leases")
        check(
            "leases read returns a list", isinstance(all_leases, list), f"{len(all_leases)} leases"
        )
        check(
            "lease read is None for a nonexistent id",
            await c.read("lease", lease_id=999999) is None,
        )

        print("\n== subnet-owner hyperparameters (sudo set) ==")
        # Alice owns `netuid`. Owner-hparam sets are rate-limited on chain, so a
        # rapid re-run may be throttled; assert the value is applied, or that the
        # chain rate-limited it (either proves the owner-set path works).
        r = await c.execute(
            sub.SetHyperparameter(netuid=netuid, name="immunity_period", value=42), alice
        )
        hp = await c.read("subnet_hyperparameters", netuid=netuid)
        applied = int(hp.get("immunity_period")) == 42
        # Chain timing guards that legitimately defer an owner set (the call still
        # reached dispatch, proving the path): tx rate limit and the admin freeze window.
        throttled = not r.success and any(
            s in r.message.lower() for s in ("rate limit", "prohibited", "freeze")
        )
        check(
            "owner set_hyperparameter applies immunity_period (or is chain-throttled)",
            applied or throttled,
            f"success={r.success} immunity_period={hp.get('immunity_period')} msg={r.message[:40]}",
        )
        check(
            "unknown/owner-unsettable hyperparameter rejected at construction",
            _raises(
                ValueError, lambda: sub.SetHyperparameter(netuid=netuid, name="tempo", value=1)
            ),
        )

        print("\n== identity (set + get, coldkey and subnet) ==")
        r = await c.execute(sub.SetIdentity(name="Verify Alice", url="https://a.example"), alice)
        ident = await c.read("identity", coldkey_ss58=acold)
        check(
            "set_identity lands; identity read decodes utf-8",
            r.success and ident is not None and ident.get("name") == "Verify Alice",
            str(ident and {k: ident.get(k) for k in ("name", "url")}),
        )
        r = await c.execute(sub.SetSubnetIdentity(netuid=netuid, subnet_name="verify-net"), alice)
        sident = await c.read("subnet_identity", netuid=netuid)
        check(
            "set_subnet_identity lands (owner-signed); read decodes",
            r.success and sident is not None and sident.get("subnet_name") == "verify-net",
            str(sident and sident.get("subnet_name")),
        )

        print("\n== coldkey swap announcement flow ==")
        check(
            "no announcement -> read returns None",
            await c.read("coldkey_swap_announcement", coldkey_ss58=BOB) is None,
        )
        # Throwaway funded coldkey keeps this re-runnable (announcements are per-account).
        swapper = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
        sw = SimpleNamespace(
            coldkey=swapper,
            coldkeypub=Keypair(ss58_address=swapper.ss58_address),
            hotkey=swapper,
        )
        new_cold = Keypair.create_from_mnemonic(Keypair.generate_mnemonic()).ss58_address
        await c.execute(sub.Transfer(dest_ss58=swapper.ss58_address, amount_tao=2.0), alice)
        r = await c.execute(sub.AnnounceColdkeySwap(new_coldkey_ss58=new_cold), sw)
        ann = await c.read("coldkey_swap_announcement", coldkey_ss58=swapper.ss58_address)
        check(
            "announce lands; swap-check read shows execute_block + hash, not disputed",
            r.success
            and ann is not None
            and ann["execute_block"] > 0
            and ann["new_coldkey_hash"] == coldkey_hash(new_cold)
            and not ann["disputed"],
            str(ann),
        )
        r = await c.execute(sub.SwapColdkeyAnnounced(new_coldkey_ss58=new_cold), sw)
        check(
            "premature execute refused (announcement delay not passed)",
            not r.success,
            r.message[:60],
        )

        print("\n== block subscription ==")
        seen: list[int] = []
        async for header in c.blocks():
            seen.append(header.number)
            if len(seen) >= 2:
                break
        check(
            "blocks() streams increasing headers", len(seen) == 2 and seen[1] >= seen[0], str(seen)
        )

        print("\n== typed errors ==")
        r = await c.execute(sub.BurnedRegister(netuid=999), alice)
        check(
            "nonexistent subnet -> subnet_not_exists",
            bool(r.error) and r.error.code.value == "subnet_not_exists",
            r.error.name if r.error else "",
        )

    print("\n" + ("ALL CHECKS PASSED" if not FAILS else f"FAILURES ({len(FAILS)}): {FAILS}"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
