"""Adapter contract, broker, authorization, output, and replay boundaries."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
import tempfile
import time
import unittest
from typing import Any

from elmos_foundry.adapters import (
    AdapterBinding,
    AdapterRegistry,
    EffectClass,
    ExternalAdapterRoute,
    ExternalExecutionBroker,
    InvocationPermit,
    InvocationRequest,
)
from elmos_foundry.canonical import canonical_digest
from elmos_foundry.domain import TenantScope
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.service import FoundryService
from elmos_foundry.store import FoundryStore


BrokerHandler = Callable[
    [InvocationRequest, Mapping[str, Any], TenantScope], Mapping[str, Any]
]


class RuntimeBoundaryTests(unittest.TestCase):
    BROKER_ID = "broker.test.sandbox"
    BROKER_VERSION = "1.0.0"
    BROKER_DIGEST = "8" * 64
    ROUTE = ExternalAdapterRoute(
        route_id="route.test.provider",
        version="1.0.0",
        digest="9" * 64,
        operation="provider-write",
    )

    @classmethod
    def setUpClass(cls) -> None:
        baseline = FoundryService()
        cls.skill_name = "architecture-decision-record"
        record = baseline.skills.get_skill_record(cls.skill_name)
        if record is None:
            raise RuntimeError("exact test Skill is absent")
        cls.outputs_by_skill = {
            name: tuple(str(item) for item in row["outputs"])
            for name, row in baseline.skills.snapshot.atomic_skills.items()
        }
        cls.binding = AdapterBinding(
            adapter_id="adapter.test.external",
            version="1.0.0",
            digest="e" * 64,
            exact_skills=(cls.skill_name,),
            effect_class=EffectClass.EXTERNAL_MUTATION,
        )
        cls.critical_skill = next(
            name
            for name, row in baseline.skills.snapshot.atomic_skills.items()
            if row["risk_class"] == "critical"
        )

    @staticmethod
    def _verifier(
        permit: InvocationPermit,
        binding: AdapterBinding,
        scope: TenantScope,
        request: InvocationRequest,
    ) -> bool:
        return (
            permit.authorization_id == "authz-001"
            and permit.adapter_digest == binding.digest
            and permit.broker_digest == request.broker_digest
            and permit.route_digest == request.route_digest
            and permit.tenant_id == scope.tenant_id
            and permit.project_id == scope.project_id
            and permit.payload_digest == request.payload_digest
            and permit.authorized_tools == request.allowed_tools
            and permit.authorized_gates == request.required_gates
        )

    def _success(self, request: InvocationRequest) -> Mapping[str, Any]:
        outputs = {
            name: {
                "status": "PRODUCED",
                "content_digest": canonical_digest(
                    {"request": request.binding_digest, "output": name}
                ),
            }
            for name in self.outputs_by_skill[request.skill_name]
        }
        receipt_body = {"request": request.binding_digest, "outcome": "CONFIRMED"}
        return {
            "status": "SUCCEEDED",
            "outputs": outputs,
            "provider_receipt": {
                "request_binding_digest": request.binding_digest,
                "receipt_digest": canonical_digest(receipt_body),
                "outcome": "CONFIRMED",
            },
            "certification_status": "NOT_CERTIFIED",
        }

    def _registry(
        self,
        *,
        binding: AdapterBinding | None = None,
        handler: BrokerHandler | None = None,
        permit_verifier: Callable[
            [InvocationPermit, AdapterBinding, TenantScope, InvocationRequest], bool
        ]
        | None = None,
        result_verifier: Callable[..., bool] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> AdapterRegistry:
        selected_handler = handler or (
            lambda request, payload, scope: self._success(request)
        )

        def execute(
            route: ExternalAdapterRoute,
            selected_binding: AdapterBinding,
            request: InvocationRequest,
            permit: InvocationPermit,
            payload: Mapping[str, Any],
            scope: TenantScope,
        ) -> Mapping[str, Any]:
            self.assertEqual(route, self.ROUTE)
            self.assertEqual(selected_binding.adapter_id, permit.adapter_id)
            return selected_handler(request, payload, scope)

        def verify_result(
            route: ExternalAdapterRoute,
            selected_binding: AdapterBinding,
            request: InvocationRequest,
            permit: InvocationPermit,
            result: Mapping[str, Any],
            scope: TenantScope,
        ) -> bool:
            if result_verifier is not None:
                return result_verifier(
                    route, selected_binding, request, permit, result, scope
                )
            receipt = result.get("provider_receipt")
            return (
                isinstance(receipt, Mapping)
                and receipt.get("request_binding_digest") == request.binding_digest
                and receipt.get("outcome") == "CONFIRMED"
            )

        broker = ExternalExecutionBroker(
            broker_id=self.BROKER_ID,
            version=self.BROKER_VERSION,
            digest=self.BROKER_DIGEST,
            execute=execute,
            verify_result=verify_result,
        )
        registry = AdapterRegistry(
            permit_verifier=permit_verifier or self._verifier,
            external_broker=broker,
            clock=clock,
        )
        registry.register(binding or self.binding, self.ROUTE)
        return registry

    def _service(
        self, registry: AdapterRegistry, *, durable: bool = True
    ) -> tuple[FoundryService, TenantScope]:
        kernel = ExecutionKernel()
        store = None
        if durable:
            directory = tempfile.TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            store = FoundryStore(
                Path(directory.name) / "external-ledger.sqlite3",
                context_verifier=kernel.require_context,
            )
            self.addCleanup(store.close)
        service = FoundryService(kernel=kernel, adapter_registry=registry, store=store)
        scope = kernel.mint_context(
            tenant_id="tenant-adapter-01",
            project_id="project-adapter-01",
            actor_id="actor-adapter-01",
            environment_id="env-adapter-01",
            workspace_digest="sha256:" + "4" * 64,
            revision_set_id="sha256:" + "d" * 64,
            purpose="adapter-boundary-tests",
            capabilities=(
                "foundry.adapter.execute",
                "foundry.store.read",
                "foundry.store.write",
            ),
            ttl_seconds=600,
            invocation_id="invocation-001",
            lease_id="lease-adapter-01",
        )
        return service, scope

    def _payload(
        self,
        service: FoundryService,
        *,
        skill_name: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        record = service.skills.get_skill_record(skill_name or self.skill_name)
        assert record is not None
        payload: dict[str, Any] = {
            "operation": "provider-write",
            "inputs": {
                str(name): {"value": f"bound-input-{index}"}
                for index, name in enumerate(record["inputs"])
            },
        }
        payload.update(fields)
        return payload

    def _permit(
        self,
        service: FoundryService,
        scope: TenantScope,
        payload: Mapping[str, Any],
        *,
        skill_name: str | None = None,
        binding: AdapterBinding | None = None,
        **changes: object,
    ) -> InvocationPermit:
        selected_skill = skill_name or self.skill_name
        selected_binding = binding or self.binding
        record = service.skills.get_skill_record(selected_skill)
        assert record is not None
        values: dict[str, object] = {
            "permit_id": "permit-001",
            "authorization_id": "authz-001",
            "invocation_id": scope.invocation_id,
            "adapter_id": selected_binding.adapter_id,
            "adapter_version": selected_binding.version,
            "adapter_digest": selected_binding.digest,
            "broker_id": self.BROKER_ID,
            "broker_version": self.BROKER_VERSION,
            "broker_digest": self.BROKER_DIGEST,
            "route_id": self.ROUTE.route_id,
            "route_digest": self.ROUTE.digest,
            "skill_name": selected_skill,
            "tenant_id": scope.tenant_id,
            "project_id": scope.project_id,
            "actor_id": scope.actor_id,
            "effect_class": selected_binding.effect_class,
            "operation": payload["operation"],
            "payload_digest": canonical_digest(payload),
            "purpose": scope.purpose,
            "environment_id": scope.environment_id,
            "workspace_digest": scope.workspace_digest,
            "revision_set_id": scope.revision_set_id,
            "issued_at": scope.issued_at,
            "expires_at": scope.expires_at,
            "nonce": "nonce-001",
            "policy_decision_id": "policy-decision-001",
            "policy_decision_digest": "sha256:" + "a" * 64,
            "authorized_tools": tuple(sorted(record["allowed_tools"])),
            "authorized_gates": tuple(sorted(record["required_gates"])),
            "gate_evidence_digest": "sha256:" + "b" * 64,
            "critical_approval_id": (
                "critical-approval-001" if record["risk_class"] == "critical" else None
            ),
            "critical_approval_digest": (
                "sha256:" + "c" * 64 if record["risk_class"] == "critical" else None
            ),
            "authorized": True,
        }
        values.update(changes)
        return InvocationPermit(**values)  # type: ignore[arg-type]

    def test_missing_adapter_is_requires_adapter_and_not_run(self) -> None:
        service, scope = self._service(AdapterRegistry())
        result = service.execute_skill(
            self.skill_name,
            {"operation": "provider-write"},
            tenant_scope=scope,
            invocation_id=scope.invocation_id,
        )
        self.assertEqual(result.outputs["outcome"], "REQUIRES_ADAPTER")
        self.assertFalse(result.external_effects_performed)

    def test_external_registration_rejects_direct_python_callable(self) -> None:
        registry = AdapterRegistry()
        with self.assertRaisesRegex(TypeError, "non-executable"):
            registry.register(self.binding, lambda *_: {"status": "SUCCEEDED"})

    def test_missing_broker_blocks_before_any_execution_claim(self) -> None:
        registry = AdapterRegistry(permit_verifier=self._verifier)
        registry.register(self.binding, self.ROUTE)
        service, scope = self._service(registry)
        payload = self._payload(service)
        result = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(service, scope, payload),
        )
        self.assertEqual(result.outputs["outcome"], "NOT_RUN")
        self.assertEqual(result.outputs["local_maximum_decision"], "NOT_READY")
        self.assertIn("broker", result.outputs["reason"])

    def test_route_operation_mismatch_blocks_before_broker_and_ledger(self) -> None:
        calls: list[str] = []
        registry = self._registry(
            handler=lambda request, payload, scope: calls.append(
                str(payload["operation"])
            )
            or self._success(request)
        )
        service, scope = self._service(registry)
        mismatched_payload = self._payload(service, operation="provider-read")
        mismatched = service.execute_skill(
            self.skill_name,
            mismatched_payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(service, scope, mismatched_payload),
        )
        self.assertEqual(mismatched.outputs["outcome"], "NOT_RUN")
        self.assertIn("route", mismatched.outputs["reason"])
        self.assertFalse(mismatched.external_effects_performed)
        self.assertFalse(calls)

        matching_payload = self._payload(service)
        matching = service.execute_skill(
            self.skill_name,
            matching_payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(service, scope, matching_payload),
        )
        self.assertEqual(matching.outputs["outcome"], "SUCCEEDED")
        self.assertEqual(calls, ["provider-write"])

    def test_missing_durable_store_blocks_external_execution(self) -> None:
        calls: list[str] = []
        registry = self._registry(
            handler=lambda request, payload, scope: calls.append(request.invocation_id)
            or self._success(request)
        )
        service, scope = self._service(registry, durable=False)
        payload = self._payload(service)
        result = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(service, scope, payload),
        )
        self.assertIn("durable", result.outputs["reason"])
        self.assertFalse(calls)

    def test_changed_payload_and_scope_are_not_covered_by_permit(self) -> None:
        for field, value in (
            ("payload", "changed"),
            ("environment_id", "env-wrong"),
            ("workspace_digest", "sha256:" + "7" * 64),
            ("revision_set_id", "sha256:" + "8" * 64),
            ("purpose", "wrong-purpose"),
            ("broker_digest", "7" * 64),
            ("route_digest", "6" * 64),
        ):
            with self.subTest(field=field):
                calls: list[str] = []
                registry = self._registry(
                    handler=lambda request, payload, scope: calls.append(request.invocation_id)
                    or self._success(request)
                )
                service, scope = self._service(registry)
                authorized = self._payload(service)
                invocation = dict(authorized)
                changes: dict[str, object] = {}
                if field == "payload":
                    invocation["changed"] = value
                else:
                    changes[field] = value
                result = service.execute_skill(
                    self.skill_name,
                    invocation,
                    tenant_scope=scope,
                    adapter_id=self.binding.adapter_id,
                    invocation_id=scope.invocation_id,
                    permit=self._permit(service, scope, authorized, **changes),
                )
                self.assertEqual(result.outputs["outcome"], "NOT_RUN")
                self.assertFalse(calls)

    def test_replay_and_same_invocation_with_changed_permit_are_blocked(self) -> None:
        calls: list[str] = []
        registry = self._registry(
            handler=lambda request, payload, scope: calls.append(request.invocation_id)
            or self._success(request)
        )
        service, scope = self._service(registry)
        payload = self._payload(service)
        permit = self._permit(service, scope, payload)
        first = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=permit,
        )
        replay = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=permit,
        )
        changed = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(
                service, scope, payload, permit_id="permit-002", nonce="nonce-002"
            ),
        )
        self.assertEqual(first.outputs["outcome"], "SUCCEEDED")
        self.assertIn("replay", replay.outputs["reason"])
        self.assertIn("idempotency", changed.outputs["reason"])
        self.assertEqual(calls, [scope.invocation_id])

    def test_expired_permit_is_blocked(self) -> None:
        calls: list[str] = []
        registry = self._registry(
            handler=lambda request, payload, scope: calls.append(request.invocation_id)
            or self._success(request),
            clock=lambda: 2_000_000_000,
        )
        service, scope = self._service(registry)
        payload = self._payload(service)
        result = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(
                service,
                scope,
                payload,
                issued_at=scope.issued_at,
                expires_at=scope.issued_at + 1,
            ),
        )
        self.assertIn("expired", result.outputs["reason"])
        self.assertFalse(calls)

    def test_missing_declared_input_and_tool_authority_are_blocked(self) -> None:
        calls: list[str] = []
        registry = self._registry(
            handler=lambda request, payload, scope: calls.append(request.invocation_id)
            or self._success(request)
        )
        service, scope = self._service(registry)
        payload = self._payload(service)
        incomplete = dict(payload)
        supplied = dict(payload["inputs"])
        supplied.pop(next(iter(supplied)))
        incomplete["inputs"] = supplied
        missing_input = service.execute_skill(
            self.skill_name,
            incomplete,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(service, scope, incomplete),
        )
        missing_tools = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(service, scope, payload, authorized_tools=()),
        )
        self.assertIn("missing required inputs", missing_input.outputs["reason"])
        self.assertIn("authorized_tools", missing_tools.outputs["reason"])
        self.assertFalse(calls)

    def test_local_adapter_requires_inputs_and_exact_declared_outputs(self) -> None:
        calls: list[str] = []
        local_binding = AdapterBinding(
            adapter_id="adapter.test.local",
            version="1.0.0",
            digest="d" * 64,
            exact_skills=(self.skill_name,),
            effect_class=EffectClass.LOCAL_DETERMINISTIC,
        )
        registry = AdapterRegistry()
        registry.register(
            local_binding,
            lambda skill, payload, scope, invocation: calls.append(invocation)
            or {"status": "SUCCEEDED"},
        )
        service, scope = self._service(registry)
        incomplete = service.execute_skill(
            self.skill_name,
            {"operation": "local-evaluate", "inputs": {}},
            tenant_scope=scope,
            adapter_id=local_binding.adapter_id,
            invocation_id=scope.invocation_id,
        )
        complete = service.execute_skill(
            self.skill_name,
            self._payload(service),
            tenant_scope=scope,
            adapter_id=local_binding.adapter_id,
            invocation_id=scope.invocation_id,
        )
        self.assertIn("missing required inputs", incomplete.outputs["reason"])
        self.assertEqual(complete.status, "FAILED")
        self.assertIn("declared outputs", complete.error or "")
        self.assertEqual(calls, [scope.invocation_id])

    def test_external_success_without_declared_outputs_is_not_confirmed(self) -> None:
        registry = self._registry(
            handler=lambda request, payload, scope: {
                **self._success(request),
                "outputs": {},
            }
        )
        service, scope = self._service(registry)
        payload = self._payload(service)
        result = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(service, scope, payload),
        )
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.outputs["effect_outcome"], "UNKNOWN")
        self.assertTrue(result.external_effects_performed)
        self.assertIn("declared output contract", result.error or "")

    def test_critical_gate_and_approval_omissions_fail_closed(self) -> None:
        critical_binding = AdapterBinding(
            adapter_id="adapter.test.critical",
            version="1.0.0",
            digest="f" * 64,
            exact_skills=(self.critical_skill,),
            effect_class=EffectClass.PRIVILEGED_EXTERNAL,
        )
        calls: list[str] = []
        registry = self._registry(
            binding=critical_binding,
            handler=lambda request, payload, scope: calls.append(request.invocation_id)
            or self._success(request),
        )
        service, scope = self._service(registry)
        payload = self._payload(service, skill_name=self.critical_skill)
        missing_gates = service.execute_skill(
            self.critical_skill,
            payload,
            tenant_scope=scope,
            adapter_id=critical_binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(
                service,
                scope,
                payload,
                skill_name=self.critical_skill,
                binding=critical_binding,
                authorized_gates=(),
            ),
        )
        missing_approval = service.execute_skill(
            self.critical_skill,
            payload,
            tenant_scope=scope,
            adapter_id=critical_binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(
                service,
                scope,
                payload,
                skill_name=self.critical_skill,
                binding=critical_binding,
                critical_approval_id=None,
                critical_approval_digest=None,
            ),
        )
        self.assertIn("authorized_gates", missing_gates.outputs["reason"])
        self.assertIn("critical", missing_approval.outputs["reason"])
        self.assertFalse(calls)

    def test_denied_or_broken_permit_verifier_never_calls_broker(self) -> None:
        for verifier in (
            lambda *_: False,
            lambda *_: (_ for _ in ()).throw(RuntimeError("broken")),
        ):
            with self.subTest(verifier=verifier):
                calls: list[str] = []
                registry = self._registry(
                    permit_verifier=verifier,
                    handler=lambda request, payload, scope: calls.append(request.invocation_id)
                    or self._success(request),
                )
                service, scope = self._service(registry)
                payload = self._payload(service)
                result = service.execute_skill(
                    self.skill_name,
                    payload,
                    tenant_scope=scope,
                    adapter_id=self.binding.adapter_id,
                    invocation_id=scope.invocation_id,
                    permit=self._permit(service, scope, payload),
                )
                self.assertEqual(result.outputs["outcome"], "NOT_RUN")
                self.assertFalse(calls)

    def test_exact_broker_request_and_verified_receipt_allow_once(self) -> None:
        calls: list[str] = []
        observed: list[InvocationRequest] = []

        def handler(
            request: InvocationRequest, payload: Mapping[str, Any], scope: TenantScope
        ) -> Mapping[str, Any]:
            calls.append(request.invocation_id)
            observed.append(request)
            return self._success(request)

        registry = self._registry(handler=handler)
        service, scope = self._service(registry)
        payload = self._payload(service)
        result = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=self._permit(service, scope, payload),
        )
        self.assertEqual(result.status, "SUCCESS")
        self.assertEqual(calls, [scope.invocation_id])
        self.assertEqual(observed[0].payload_digest, canonical_digest(payload))
        self.assertEqual(observed[0].broker_digest, self.BROKER_DIGEST)
        self.assertEqual(result.outputs["effect_outcome"], "CONFIRMED")
        self.assertEqual(
            result.outputs["external_evidence_status"], "PROVIDER_RECEIPT_VERIFIED"
        )
        self.assertEqual(result.outputs["certification_status"], "NOT_CERTIFIED")
        self.assertTrue(result.external_effects_performed)

    def test_missing_or_denied_provider_receipt_is_unknown_failure(self) -> None:
        handlers: tuple[BrokerHandler, ...] = (
            lambda request, payload, scope: {
                "status": "SUCCEEDED",
                "outputs": self._success(request)["outputs"],
            },
            lambda request, payload, scope: self._success(request),
        )
        verifiers = (None, lambda *_: False)
        for handler, verifier in zip(handlers, verifiers, strict=True):
            with self.subTest(verifier=verifier):
                registry = self._registry(handler=handler, result_verifier=verifier)
                service, scope = self._service(registry)
                payload = self._payload(service)
                result = service.execute_skill(
                    self.skill_name,
                    payload,
                    tenant_scope=scope,
                    adapter_id=self.binding.adapter_id,
                    invocation_id=scope.invocation_id,
                    permit=self._permit(service, scope, payload),
                )
                self.assertEqual(result.status, "FAILED")
                self.assertEqual(result.outputs["effect_outcome"], "UNKNOWN")
                self.assertTrue(result.external_effects_performed)

    def test_uncertain_external_failure_is_persisted_and_not_retried(self) -> None:
        calls: list[str] = []

        def uncertain(
            request: InvocationRequest, payload: Mapping[str, Any], scope: TenantScope
        ) -> Mapping[str, Any]:
            calls.append(request.invocation_id)
            raise TimeoutError("provider outcome unavailable")

        registry = self._registry(handler=uncertain)
        service, scope = self._service(registry)
        payload = self._payload(service)
        permit = self._permit(service, scope, payload)
        first = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=permit,
        )
        repeated = service.execute_skill(
            self.skill_name,
            payload,
            tenant_scope=scope,
            adapter_id=self.binding.adapter_id,
            invocation_id=scope.invocation_id,
            permit=permit,
        )
        self.assertEqual(first.outputs["effect_outcome"], "UNKNOWN")
        self.assertTrue(first.external_effects_performed)
        self.assertEqual(repeated.outputs["outcome"], "NOT_RUN")
        self.assertEqual(calls, [scope.invocation_id])

    def test_skill_adapter_ownership_cannot_collide(self) -> None:
        registry = self._registry()
        collision = AdapterBinding(
            adapter_id="adapter.test.collision",
            version="1.0.0",
            digest="f" * 64,
            exact_skills=(self.skill_name,),
            effect_class=EffectClass.EXTERNAL_READ,
        )
        with self.assertRaises(ValueError):
            registry.register(collision, self.ROUTE)


if __name__ == "__main__":
    unittest.main()
