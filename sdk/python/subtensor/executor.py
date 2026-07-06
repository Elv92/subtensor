"""The single choke point for executing intents.

Everything that mutates chain state flows through here: build the call once,
simulate the fee, gather predicted effects/warnings, enforce policy, and only
then sign and submit. ``plan`` does all of that except submitting; ``execute``
adds the submission (and refuses if policy is violated).
"""

from __future__ import annotations

from typing import Any, Optional

from bittensor_drand import encrypt_mlkem768

from ._generated import calls as generated_calls
from ._substrate import Substrate
from .intents import Intent, Plan, Policy
from .intents import build as build_intent
from .intents import list_tools
from .intents.base import BuiltCall
from .intents.proxy import check_proxy_type
from .result import ChainError, ExtrinsicResult, PolicyError, chain_error_from_dispatch
from .settings import DEFAULT_ERA_PERIOD, MEV_SHIELD_ERA_PERIOD
from .signing import public_view, resolve_signer


def _proxy_inner_error(events: list) -> Optional[Any]:
    """The ``Err`` payload of a ``Proxy.ProxyExecuted`` event, or None.

    A proxied extrinsic *succeeds* even when the wrapped call fails — the inner
    outcome is only reported through this event, so it must be checked.
    """
    for entry in events:
        record = entry.value if hasattr(entry, "value") else entry
        event = record.get("event", record) if isinstance(record, dict) else {}
        if event.get("module_id") != "Proxy" or event.get("event_id") != "ProxyExecuted":
            continue
        attributes = event.get("attributes")
        result = attributes.get("result") if isinstance(attributes, dict) else attributes
        if isinstance(result, dict) and "Err" in result:
            return result["Err"]
    return None


class Executor:
    def __init__(self, substrate: Substrate, policy: Optional[Policy] = None):
        self.substrate = substrate
        self.policy = policy

    @staticmethod
    def _public_keypair(wallet: Any, signer: str):
        """The signer's public keypair — enough to address and to estimate fees,
        without unlocking the private coldkey."""
        return public_view(wallet, signer)

    async def plan(
        self,
        intent: Intent,
        wallet: Any,
        *,
        policy: Optional[Policy] = None,
        proxy_for: Optional[str] = None,
        proxy_type: Optional[str] = None,
    ) -> Plan:
        """Dry-run: build the call, simulate the fee, and check policy. No submit.

        ``proxy_for`` switches to proxy signing: the call is wrapped in
        ``Proxy.proxy(real=proxy_for)`` so it dispatches with that account's
        origin, while the *local* wallet key (which must be a registered proxy of
        ``proxy_for``) signs. ``proxy_type`` optionally forces the exact proxy
        type to match (``force_proxy_type``).
        """
        built = await intent.build(self.substrate, wallet)
        if isinstance(built, BuiltCall):
            call, extras = built.call, built.extras
        else:
            call, extras = built, {}
        pub = self._public_keypair(wallet, intent.signer)
        signer_address = pub.ss58_address
        # The account whose state the call actually touches.
        origin = proxy_for or signer_address

        if proxy_for is not None:
            if proxy_type is not None:
                check_proxy_type(proxy_type)
            call = await self.substrate.compose(
                generated_calls.Proxy.proxy(real=proxy_for, force_proxy_type=proxy_type, call=call)
            )
            extras = {**extras, "proxy_for": proxy_for}

        warnings: list[str] = list(await intent.warnings(self.substrate, origin))
        fee = None
        try:
            fee = await self.substrate.estimate_fee(call, pub)
        except Exception as error:  # fee estimation is best-effort
            warnings.append(f"could not estimate fee: {error}")

        effects = list(await intent.effects(self.substrate, origin))
        if proxy_for is not None:
            effects.append(f"dispatched via proxy as {proxy_for} (signed by {signer_address})")
        active_policy = policy or self.policy
        violations = active_policy.check(intent, fee) if active_policy else []

        return Plan(
            op=intent.op,
            summary=intent.summary(),
            signer=intent.signer,
            signer_address=signer_address,
            fee=fee,
            effects=effects,
            warnings=warnings,
            violations=violations,
            call=call,
            extras=extras,
        )

    async def execute(
        self,
        intent: Intent,
        wallet: Any,
        *,
        policy: Optional[Policy] = None,
        proxy_for: Optional[str] = None,
        proxy_type: Optional[str] = None,
        period: Optional[int] = DEFAULT_ERA_PERIOD,
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = True,
    ) -> ExtrinsicResult:
        """Plan, then sign and submit. Raises ``PolicyError`` if the plan violates
        policy. (To preview without submitting, call ``plan`` instead.)

        With ``proxy_for``, the local wallet key signs a ``Proxy.proxy`` wrapper
        and the call dispatches as ``proxy_for`` — the real account's key never
        touches this machine (see ``plan``).
        """
        plan = await self.plan(
            intent, wallet, policy=policy, proxy_for=proxy_for, proxy_type=proxy_type
        )
        if not plan.ok:
            raise PolicyError(plan.violations)

        keypair = resolve_signer(wallet, intent.signer)
        result = await self.substrate.submit(
            plan.call,
            keypair,
            period=period,
            wait_for_inclusion=wait_for_inclusion,
            wait_for_finalization=wait_for_finalization,
        )
        if proxy_for is not None and result.success:
            inner_error = _proxy_inner_error(result.events)
            if inner_error is not None:
                error = chain_error_from_dispatch(inner_error)
                result.success = False
                result.message = f"proxied call failed: {error.message}"
                result.error = error
        if result.success and plan.extras:
            result.data.update(plan.extras)
        return result

    async def execute_tool(self, op: str, args: dict, wallet: Any, **kwargs) -> ExtrinsicResult:
        """Build an intent by name from a dict of args, then execute it."""
        return await self.execute(build_intent(op, args), wallet, **kwargs)

    async def submit_shielded(
        self,
        intent: Intent,
        wallet: Any,
        *,
        policy: Optional[Policy] = None,
        period: int = MEV_SHIELD_ERA_PERIOD,
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = False,
    ) -> ExtrinsicResult:
        """Submit an intent MEV-shielded via the MevShield pallet.

        The intent's call is signed as an inner extrinsic (at nonce+1), encrypted
        with the chain's rotating ML-KEM-768 key (``NextKey``), and carried inside
        ``MevShield.submit_encrypted`` (signed at nonce). It stays encrypted in the
        pool until the block author decrypts and executes it, so the mempool can't
        front-run it. Policy is enforced on the intent before anything is signed.
        """
        built = await intent.build(self.substrate, wallet)
        call = built.call if isinstance(built, BuiltCall) else built
        active_policy = policy or self.policy
        if active_policy is not None:
            violations = active_policy.check(intent, None)
            if violations:
                raise PolicyError(violations)

        pubkey = await self.substrate.mev_next_key()
        if not pubkey:
            raise ChainError("MEV Shield NextKey not available; is the MevShield pallet active?")

        keypair = resolve_signer(wallet, intent.signer)
        nonce = await self.substrate.raw.get_account_next_index(keypair.ss58_address)
        inner_bytes, inner_hash = await self.substrate.sign_extrinsic(
            call, keypair, nonce=nonce + 1, period=period
        )
        ciphertext = encrypt_mlkem768(pubkey, inner_bytes, include_key_hash=True)
        outer = await self.substrate.compose(
            generated_calls.MevShield.submit_encrypted(ciphertext=ciphertext)
        )
        result = await self.substrate.submit(
            outer,
            keypair,
            nonce=nonce,
            period=period,
            wait_for_inclusion=wait_for_inclusion,
            wait_for_finalization=wait_for_finalization,
        )
        if result.success:
            result.data.update({"shielded": True, "inner_extrinsic_hash": inner_hash})
        return result

    async def submit_call(
        self,
        call,
        wallet: Any,
        *,
        signer: str = "coldkey",
        policy: Optional[Policy] = None,
        period: Optional[int] = DEFAULT_ERA_PERIOD,
        wait_for_inclusion: bool = True,
        wait_for_finalization: bool = True,
    ) -> ExtrinsicResult:
        """Escape hatch: sign and submit a generated raw call with no intent wrapper.

        ``call`` is any builder from ``subtensor.calls`` (every extrinsic the chain
        exposes, including ones no intent wraps). There is no plan/preview, so an
        active policy cannot bound the spend — raw calls are refused unless the
        policy sets ``allow_raw_calls=True``. No policy means no restriction,
        exactly as for intents.
        """
        active_policy = policy or self.policy
        if active_policy is not None and not active_policy.allow_raw_calls:
            raise PolicyError(
                ["raw call submission is disabled by policy (set allow_raw_calls=True)"]
            )
        composed = await self.substrate.compose(call)
        keypair = resolve_signer(wallet, signer)
        return await self.substrate.submit(
            composed,
            keypair,
            period=period,
            wait_for_inclusion=wait_for_inclusion,
            wait_for_finalization=wait_for_finalization,
        )

    def tools(self) -> list[dict]:
        """The machine-readable catalog of every executable operation."""
        return list_tools()
