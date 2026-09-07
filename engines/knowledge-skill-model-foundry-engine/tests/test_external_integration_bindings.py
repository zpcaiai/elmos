"""Coverage for exact Skill and pipeline host integration bindings."""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
import time
from typing import ClassVar

from elmos_foundry.adapters import ExternalExecutionBroker, InvocationPermit
from elmos_foundry.canonical import canonical_digest
from elmos_foundry.domain import TenantScope
from elmos_foundry.kernel import ExecutionKernel
from elmos_foundry.local_semantics import LOCAL_SEMANTIC_SKILLS
from elmos_foundry.pipelines import PIPELINE_PROFILE_REGISTRY
from elmos_foundry.service import FoundryService
from elmos_foundry.store import FoundryStore


class ExternalIntegrationBindingTests(unittest.TestCase):
    service: ClassVar[FoundryService]
    scope: ClassVar[TenantScope]

    @classmethod
    def setUpClass(cls) -> None:
        cls.service = FoundryService()
        cls.scope = cls.service.kernel.mint_context(
            tenant_id="tenant-integration-01",
            project_id="project-integration-01",
            actor_id="actor-integration-01",
            environment_id="environment-integration-01",
            workspace_digest="sha256:" + "8" * 64,
            revision_set_id="sha256:" + "9" * 64,
            purpose="integration-binding-tests",
            capabilities=(
                "foundry.adapter.execute",
                "foundry.pipeline.execute",
                "foundry.pipeline.prepare",
            ),
            ttl_seconds=600,
            invocation_id="inv-integration-01",
            lease_id="lease-integration-01",
        )

    def test_every_non_local_skill_has_one_unique_privileged_route(self) -> None:
        records = self.service.skills.snapshot.atomic_skills
        expected = set(records) - set(LOCAL_SEMANTIC_SKILLS)
        rows = [
            row
            for row in self.service.status()["adapters"]
            if row["effect_class"] == "PRIVILEGED_EXTERNAL"
        ]
        bound = {
            name
            for row in rows
            for name in row["exact_skills"]
        }
        self.assertEqual(bound, expected)
        self.assertEqual(len(rows), 1_249)
        self.assertEqual(len({row["adapter_id"] for row in rows}), 1_249)
        self.assertEqual(len({row["digest"] for row in rows}), 1_249)
        for name in expected:
            binding = self.service.skills.adapters.binding_for(name)
            self.assertIsNotNone(binding)
            assert binding is not None
            self.assertEqual(binding.adapter_id, f"external.{name}")
            self.assertEqual(binding.exact_skills, (name,))
            self.assertEqual(
                binding.metadata["skill_source_sha256"],
                records[name]["source_sha256"],
            )

    def test_non_local_route_cannot_run_without_host_broker(self) -> None:
        name = "a2a-agent-discovery-messaging"
        record = self.service.skills.snapshot.atomic_skills[name]
        result = self.service.execute_skill(
            name,
            {
                "operation": f"foundry.skill.{name}.execute",
                "inputs": {key: f"value-{index}" for index, key in enumerate(record["inputs"])},
            },
            tenant_scope=self.scope,
            adapter_id=f"external.{name}",
            invocation_id=self.scope.invocation_id,
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.outputs["outcome"], "NOT_RUN")
        self.assertFalse(result.external_effects_performed)
        self.assertIn("host-owned broker", str(result.error))
        self.assertEqual(result.outputs["certification_status"], "NOT_CERTIFIED")

    def test_all_pipeline_routes_are_exact_and_prepare_exposes_binding(self) -> None:
        rows = self.service.pipelines.adapters.describe()
        self.assertEqual(len(rows), 14)
        self.assertEqual(
            {name for row in rows for name in row["exact_skills"]},
            set(PIPELINE_PROFILE_REGISTRY),
        )
        self.assertEqual(len({row["digest"] for row in rows}), 14)
        for name, profile in PIPELINE_PROFILE_REGISTRY.items():
            params = {key: f"value-{index}" for index, key in enumerate(profile.required_inputs)}
            plan = self.service.run_pipeline(name, params, tenant_scope=self.scope)
            self.assertEqual(plan["runtime_execution_mode"], "HOST_BROKER")
            self.assertEqual(plan["adapter_binding"], f"pipeline.{name}")
            self.assertEqual(plan["broker_route"], f"pipeline-route.{name}")
            self.assertEqual(plan["execution_status"], "NOT_RUN")

    def test_pipeline_execution_fails_closed_without_host_broker(self) -> None:
        name = "knowledge-to-skill"
        profile = PIPELINE_PROFILE_REGISTRY[name]
        params = {key: f"value-{index}" for index, key in enumerate(profile.required_inputs)}
        result = self.service.execute_pipeline(
            name,
            params,
            tenant_scope=self.scope,
            adapter_id=f"pipeline.{name}",
            invocation_id=self.scope.invocation_id,
        )
        self.assertEqual(result["status"], "NOT_RUN")
        self.assertFalse(result["external_effects_performed"])
        self.assertIn("host-owned broker", str(result["error"]))
        self.assertEqual(result["certification_status"], "NOT_CERTIFIED")

    def test_host_can_build_exact_skill_and_pipeline_authorization_requests(self) -> None:
        broker = ExternalExecutionBroker(
            broker_id="broker.integration.test",
            version="1.0.0",
            digest="a" * 64,
            execute=lambda *_args: {},
            verify_result=lambda *_args: False,
        )
        service = FoundryService(
            external_broker=broker,
            permit_verifier=lambda *_args: False,
        )
        scope = service.kernel.mint_context(
            tenant_id="tenant-request-01",
            project_id="project-request-01",
            actor_id="actor-request-01",
            environment_id="environment-request-01",
            workspace_digest="sha256:" + "a" * 64,
            revision_set_id="sha256:" + "b" * 64,
            purpose="permit-request-tests",
            capabilities=("foundry.adapter.execute", "foundry.pipeline.execute"),
            ttl_seconds=600,
            invocation_id="inv-request-01",
            lease_id="lease-request-01",
        )
        skill_name = "a2a-agent-discovery-messaging"
        skill_record = service.skills.snapshot.atomic_skills[skill_name]
        skill_payload = {
            "operation": f"foundry.skill.{skill_name}.execute",
            "inputs": {
                key: f"value-{index}"
                for index, key in enumerate(skill_record["inputs"])
            },
        }
        skill_request = service.prepare_external_skill_request(
            skill_name,
            skill_payload,
            tenant_scope=scope,
            adapter_id=f"external.{skill_name}",
            invocation_id=scope.invocation_id,
        )
        self.assertEqual(skill_request.skill_name, skill_name)
        self.assertEqual(skill_request.adapter_id, f"external.{skill_name}")
        self.assertEqual(skill_request.broker_id, broker.broker_id)
        self.assertEqual(skill_request.allowed_tools, tuple(sorted(skill_record["allowed_tools"])))

        pipeline_name = "knowledge-to-skill"
        profile = PIPELINE_PROFILE_REGISTRY[pipeline_name]
        pipeline_params = {
            key: f"value-{index}" for index, key in enumerate(profile.required_inputs)
        }
        pipeline_request = service.prepare_pipeline_execution_request(
            pipeline_name,
            pipeline_params,
            tenant_scope=scope,
            adapter_id=f"pipeline.{pipeline_name}",
            invocation_id=scope.invocation_id,
        )
        self.assertEqual(pipeline_request.skill_name, pipeline_name)
        self.assertEqual(pipeline_request.adapter_id, f"pipeline.{pipeline_name}")
        self.assertEqual(pipeline_request.broker_id, broker.broker_id)
        self.assertEqual(pipeline_request.allowed_tools, tuple(sorted(profile.required_adapters)))

    def test_pipeline_executes_only_with_exact_permit_store_and_verified_receipt(self) -> None:
        def execute(_route: object, _binding: object, request: object, *_args: object) -> object:
            request_digest = request.binding_digest  # type: ignore[attr-defined]
            return {
                "status": "SUCCEEDED",
                "outputs": {
                    "pipeline execution receipt": {"request_digest": request_digest},
                    "rollback outcome": {"status": "NOT_REQUIRED"},
                    "step evidence": [{"step": "host-execution", "status": "VERIFIED"}],
                },
                "provider_receipt": {
                    "request_binding_digest": request_digest,
                    "receipt_digest": canonical_digest(
                        {"request": request_digest, "outcome": "CONFIRMED"}
                    ),
                    "outcome": "CONFIRMED",
                },
                "certification_status": "NOT_CERTIFIED",
            }

        broker = ExternalExecutionBroker(
            broker_id="broker.pipeline.test",
            version="1.0.0",
            digest="c" * 64,
            execute=execute,  # type: ignore[arg-type]
            verify_result=lambda *_args: True,
        )
        kernel = ExecutionKernel()
        with tempfile.TemporaryDirectory() as directory:
            store = FoundryStore(
                Path(directory) / "pipeline.sqlite3",
                context_verifier=kernel.require_context,
            )
            self.addCleanup(store.close)
            service = FoundryService(
                kernel=kernel,
                store=store,
                external_broker=broker,
                permit_verifier=lambda *_args: True,
            )
            scope = kernel.mint_context(
                tenant_id="tenant-execute-01",
                project_id="project-execute-01",
                actor_id="actor-execute-01",
                environment_id="environment-execute-01",
                workspace_digest="sha256:" + "c" * 64,
                revision_set_id="sha256:" + "d" * 64,
                purpose="pipeline-execution-test",
                capabilities=("foundry.pipeline.execute", "foundry.store.write"),
                ttl_seconds=600,
                invocation_id="inv-execute-01",
                lease_id="lease-execute-01",
            )
            name = "knowledge-to-skill"
            profile = PIPELINE_PROFILE_REGISTRY[name]
            params = {
                key: f"value-{index}" for index, key in enumerate(profile.required_inputs)
            }
            request = service.prepare_pipeline_execution_request(
                name,
                params,
                tenant_scope=scope,
                adapter_id=f"pipeline.{name}",
                invocation_id=scope.invocation_id,
            )
            issued_at = max(scope.issued_at, int(time.time()))
            permit = InvocationPermit(
                permit_id="permit-pipeline-01",
                authorization_id="authorization-pipeline-01",
                invocation_id=request.invocation_id,
                adapter_id=request.adapter_id,
                adapter_version=request.adapter_version,
                adapter_digest=request.adapter_digest,
                broker_id=request.broker_id,
                broker_version=request.broker_version,
                broker_digest=request.broker_digest,
                route_id=request.route_id,
                route_digest=request.route_digest,
                skill_name=request.skill_name,
                tenant_id=request.tenant_id,
                project_id=request.project_id,
                actor_id=request.actor_id,
                effect_class=request.effect_class,
                operation=request.operation,
                payload_digest=request.payload_digest,
                purpose=request.purpose,
                environment_id=request.environment_id,
                workspace_digest=request.workspace_digest,
                revision_set_id=request.revision_set_id,
                issued_at=issued_at,
                expires_at=min(issued_at + 300, scope.expires_at),
                nonce="nonce-pipeline-01",
                policy_decision_id="policy-pipeline-01",
                policy_decision_digest="sha256:" + "e" * 64,
                authorized_tools=request.allowed_tools,
                authorized_gates=request.required_gates,
                gate_evidence_digest="sha256:" + "f" * 64,
                critical_approval_id="approval-pipeline-01",
                critical_approval_digest="sha256:" + "1" * 64,
                authorized=True,
            )
            result = service.execute_pipeline(
                name,
                params,
                tenant_scope=scope,
                adapter_id=f"pipeline.{name}",
                invocation_id=scope.invocation_id,
                permit=permit,
            )
            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertTrue(result["external_effects_performed"])
            self.assertEqual(result["external_evidence_status"], "PROVIDER_RECEIPT_VERIFIED")
            self.assertEqual(result["certification_status"], "NOT_CERTIFIED")


if __name__ == "__main__":
    unittest.main()
