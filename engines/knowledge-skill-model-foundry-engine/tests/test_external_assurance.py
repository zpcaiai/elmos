"""Tests for the production host and external evidence boundary."""

from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from elmos_foundry.adapters import (
    AdapterBinding,
    EffectClass,
    ExternalAdapterRoute,
    InvocationPermit,
    InvocationRequest,
)
from elmos_foundry.canonical import canonical_digest, digest_bytes
from elmos_foundry.domain import CertificationStatus, TenantScope
from elmos_foundry.external_assurance import (
    CertificationRequest,
    ExternalAssuranceError,
    ExternalRunKind,
    ExternalRunRequest,
    IndependentAcceptanceRequest,
    ProviderCommandRoute,
    build_subprocess_broker,
    evaluate_certification,
    verify_external_run_receipt,
    verify_independent_acceptance,
)


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def signed(document: dict[str, object]) -> dict[str, object]:
    result = copy.deepcopy(document)
    receipt_digest = canonical_digest(result)
    result["receipt_digest"] = receipt_digest
    result["signature"] = receipt_digest
    return result


def verifier(_authority: str, key_id: str, digest: str, signature: str) -> bool:
    return key_id == "test-key" and signature == digest


class ExternalAssuranceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scope = TenantScope(
            tenant_id="tenant-01",
            project_id="project-01",
            actor_id="actor-01",
            environment_id="environment-01",
            workspace_digest=DIGEST_A,
            revision_set_id=DIGEST_B,
            purpose="external-assurance-test",
            invocation_id="invocation-01",
            lease_id="lease-01",
            capabilities=("foundry.adapter.execute",),
            issued_at=1,
            expires_at=4_000_000_000,
            mint_authority="test-authority",
        )

    @staticmethod
    def write_provider(path: Path) -> None:
        path.write_text(
            """#!/usr/bin/env python3
import hashlib
import json
import sys

request = json.load(sys.stdin)
outputs = {"artifact": "provider-output"}
receipt = {
    "schema_version": "elmos.foundry.provider-receipt.v1",
    "provider_id": request["provider"]["provider_id"],
    "provider_version": request["provider"]["provider_version"],
    "executable_digest": request["provider"]["executable_digest"],
    "request_binding_digest": request["request_binding_digest"],
    "route_id": request["route"]["route_id"],
    "route_digest": request["route"]["route_digest"],
    "operation": request["route"]["operation"],
    "outcome": "CONFIRMED",
    "outputs_digest": "sha256:" + hashlib.sha256(
        json.dumps(outputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest(),
    "key_id": "test-key",
}
body = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
receipt["receipt_digest"] = "sha256:" + hashlib.sha256(body).hexdigest()
receipt["signature"] = receipt["receipt_digest"]
json.dump({"status": "SUCCEEDED", "outputs": outputs, "provider_receipt": receipt}, sys.stdout,
          ensure_ascii=False, sort_keys=True, separators=(",", ":"))
""",
            encoding="utf-8",
        )
        path.chmod(0o700)

    def broker_objects(
        self, broker_digest: str
    ) -> tuple[ExternalAdapterRoute, AdapterBinding, InvocationRequest, InvocationPermit]:
        route = ExternalAdapterRoute("route.provider-01", "1.0.0", "1" * 64, "execute")
        binding = AdapterBinding(
            "adapter.provider-01", "1.0.0", "2" * 64, ("skill-01",), EffectClass.EXTERNAL_MUTATION
        )
        request = InvocationRequest(
            skill_name="skill-01",
            operation="execute",
            payload_digest=canonical_digest({"inputs": {"source": "value"}}),
            tenant_id=self.scope.tenant_id,
            project_id=self.scope.project_id,
            actor_id=self.scope.actor_id,
            purpose=self.scope.purpose,
            environment_id=self.scope.environment_id,
            workspace_digest=self.scope.workspace_digest,
            revision_set_id=self.scope.revision_set_id,
            invocation_id=self.scope.invocation_id,
            adapter_id=binding.adapter_id,
            adapter_version=binding.version,
            adapter_digest=binding.digest,
            broker_id="broker.provider-01",
            broker_version="1.0.0",
            broker_digest=broker_digest,
            route_id=route.route_id,
            route_digest=route.digest,
            effect_class=binding.effect_class,
            risk_class="high",
            required_inputs=("source",),
            allowed_tools=("provider-api",),
            required_gates=("authorization",),
        )
        permit = InvocationPermit(
            permit_id="permit-01",
            authorization_id="authorization-01",
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
            issued_at=1,
            expires_at=4_000_000_000,
            nonce="nonce-01",
            policy_decision_id="policy-01",
            policy_decision_digest=DIGEST_A,
            authorized_tools=request.allowed_tools,
            authorized_gates=request.required_gates,
            gate_evidence_digest=DIGEST_B,
            authorized=True,
        )
        return route, binding, request, permit

    def test_digest_pinned_provider_process_executes_and_verifies_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "provider"
            self.write_provider(executable)
            config = ProviderCommandRoute(
                route_id="route.provider-01",
                route_digest="1" * 64,
                operation="execute",
                provider_id="provider-01",
                provider_version="2026.09",
                executable=executable,
                executable_digest=digest_bytes(executable.read_bytes()),
            )
            broker = build_subprocess_broker(
                broker_id="broker.provider-01",
                version="1.0.0",
                routes=(config,),
                receipt_verifier=verifier,
            )
            route, binding, request, permit = self.broker_objects(broker.digest)
            result = broker.execute(
                route,
                binding,
                request,
                permit,
                {"inputs": {"source": "value"}},
                self.scope,
            )
            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertTrue(
                broker.verify_result(route, binding, request, permit, result, self.scope)
            )

            executable.write_text("tampered", encoding="utf-8")
            executable.chmod(0o700)
            with self.assertRaisesRegex(ExternalAssuranceError, "digest drifted"):
                broker.execute(route, binding, request, permit, {}, self.scope)

    def test_provider_process_rejects_symlink_and_unknown_route(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            self.write_provider(target)
            link = Path(directory) / "provider"
            link.symlink_to(target)
            config = ProviderCommandRoute(
                route_id="route.provider-01",
                route_digest="1" * 64,
                operation="execute",
                provider_id="provider-01",
                provider_version="2026.09",
                executable=link,
                executable_digest=digest_bytes(target.read_bytes()),
            )
            broker = build_subprocess_broker(
                broker_id="broker.provider-01",
                version="1.0.0",
                routes=(config,),
                receipt_verifier=verifier,
            )
            route, binding, request, permit = self.broker_objects(broker.digest)
            with self.assertRaisesRegex(ExternalAssuranceError, "non-symlink"):
                broker.execute(route, binding, request, permit, {}, self.scope)

    def training_request(self) -> ExternalRunRequest:
        return ExternalRunRequest(
            ExternalRunKind.TRAINING,
            "training-request-01",
            "tenant-01",
            "project-01",
            "model-01",
            "training-environment-01",
            "training-provider-01",
            "2026.09",
            "producer-01",
            DIGEST_A,
            {"base-model": DIGEST_C, "dataset": DIGEST_B},
            ("lineage", "metrics", "model"),
        )

    def training_receipt(self, request: ExternalRunRequest) -> dict[str, object]:
        return signed(
            {
                "schema_version": "elmos.foundry.external-run-receipt.v1",
                "run_kind": "TRAINING",
                "request_id": request.request_id,
                "request_binding_digest": request.binding_digest,
                "tenant_id": request.tenant_id,
                "project_id": request.project_id,
                "target_id": request.target_id,
                "environment_id": request.environment_id,
                "provider_id": request.provider_id,
                "provider_version": request.provider_version,
                "executor_id": "trainer-01",
                "outcome": "CONFIRMED",
                "reconciliation_status": "RECONCILED",
                "output_digests": {
                    "lineage": DIGEST_C,
                    "metrics": DIGEST_A,
                    "model": DIGEST_B,
                },
                "started_at": 100,
                "finished_at": 200,
                "key_id": "test-key",
            }
        )

    def test_training_receipt_requires_exact_outputs_and_reconciliation(self) -> None:
        request = self.training_request()
        receipt = self.training_receipt(request)
        self.assertEqual(
            verify_external_run_receipt(request, receipt, verifier=verifier),
            receipt["receipt_digest"],
        )
        receipt["reconciliation_status"] = "UNKNOWN"
        with self.assertRaisesRegex(ExternalAssuranceError, "exact request"):
            verify_external_run_receipt(request, receipt, verifier=verifier)

    def test_deployment_receipt_requires_health_and_rollback_artifacts(self) -> None:
        request = ExternalRunRequest(
            ExternalRunKind.DEPLOYMENT,
            "deployment-request-01",
            "tenant-01",
            "project-01",
            "release-01",
            "production-environment-01",
            "deployment-provider-01",
            "2026.09",
            "producer-01",
            DIGEST_A,
            {"artifact": DIGEST_B, "release": DIGEST_C},
            ("deployment", "health", "rollback"),
        )
        receipt = signed(
            {
                "schema_version": "elmos.foundry.external-run-receipt.v1",
                "run_kind": "DEPLOYMENT",
                "request_id": request.request_id,
                "request_binding_digest": request.binding_digest,
                "tenant_id": request.tenant_id,
                "project_id": request.project_id,
                "target_id": request.target_id,
                "environment_id": request.environment_id,
                "provider_id": request.provider_id,
                "provider_version": request.provider_version,
                "executor_id": "deployer-01",
                "outcome": "CONFIRMED",
                "reconciliation_status": "RECONCILED",
                "output_digests": {
                    "deployment": DIGEST_A,
                    "health": DIGEST_B,
                    "rollback": DIGEST_C,
                },
                "started_at": 100,
                "finished_at": 200,
                "key_id": "test-key",
            }
        )
        self.assertEqual(
            verify_external_run_receipt(request, receipt, verifier=verifier),
            receipt["receipt_digest"],
        )
        receipt["output_digests"] = {"deployment": DIGEST_A, "health": DIGEST_B}
        with self.assertRaisesRegex(ExternalAssuranceError, "output contract"):
            verify_external_run_receipt(request, receipt, verifier=verifier)

    def acceptance_request(self, training_digest: str) -> IndependentAcceptanceRequest:
        return IndependentAcceptanceRequest(
            "acceptance-request-01",
            "tenant-01",
            "project-01",
            "model-01",
            "producer-01",
            ("trainer-01",),
            DIGEST_A,
            DIGEST_B,
            {
                "DEPLOYMENT": DIGEST_C,
                "PROVIDER": DIGEST_A,
                "TRAINING": training_digest,
            },
            ("E1", "E2", "E3"),
        )

    def acceptance_receipt(self, request: IndependentAcceptanceRequest) -> dict[str, object]:
        return signed(
            {
                "schema_version": "elmos.foundry.independent-acceptance-receipt.v1",
                "request_id": request.request_id,
                "request_binding_digest": request.binding_digest,
                "tenant_id": request.tenant_id,
                "project_id": request.project_id,
                "target_id": request.target_id,
                "evidence_bundle_digest": request.evidence_bundle_digest,
                "holdout_corpus_digest": request.holdout_corpus_digest,
                "external_receipt_digests": dict(request.external_receipt_digests),
                "verifier_id": "independent-verifier-01",
                "verdict": "PASS",
                "gate_results": {"E1": "PASS", "E2": "PASS", "E3": "PASS"},
                "skipped_cases": [],
                "unknown_cases": [],
                "key_id": "test-key",
            }
        )

    def test_acceptance_rejects_nonindependent_or_skipped_verdict(self) -> None:
        training_digest = verify_external_run_receipt(
            self.training_request(),
            self.training_receipt(self.training_request()),
            verifier=verifier,
        )
        request = self.acceptance_request(training_digest)
        receipt = self.acceptance_receipt(request)
        self.assertEqual(
            verify_independent_acceptance(request, receipt, verifier=verifier),
            receipt["receipt_digest"],
        )
        receipt["verifier_id"] = "trainer-01"
        with self.assertRaisesRegex(ExternalAssuranceError, "not organizationally separate"):
            verify_independent_acceptance(request, receipt, verifier=verifier)

        receipt = self.acceptance_receipt(request)
        receipt["skipped_cases"] = ["case-01"]
        with self.assertRaisesRegex(ExternalAssuranceError, "cannot pass"):
            verify_independent_acceptance(request, receipt, verifier=verifier)

    def certification_request(
        self, external_digest: str, acceptance_digest: str
    ) -> CertificationRequest:
        return CertificationRequest(
            "certification-request-01",
            "tenant-01",
            "project-01",
            "model-01",
            "E4_PRODUCTION_CERTIFIED",
            DIGEST_A,
            DIGEST_B,
            DIGEST_C,
            {
                "DEPLOYMENT": DIGEST_C,
                "PROVIDER": DIGEST_B,
                "TRAINING": external_digest,
            },
            acceptance_digest,
            "producer-01",
            ("trainer-01",),
            "independent-verifier-01",
        )

    def certification_receipt(self, request: CertificationRequest) -> dict[str, object]:
        return signed(
            {
                "schema_version": "elmos.foundry.certification-receipt.v1",
                "request_id": request.request_id,
                "request_binding_digest": request.binding_digest,
                "tenant_id": request.tenant_id,
                "project_id": request.project_id,
                "target_id": request.target_id,
                "certified_level": request.requested_level,
                "catalog_digest": request.catalog_digest,
                "implementation_digest": request.implementation_digest,
                "policy_digest": request.policy_digest,
                "external_receipt_digests": dict(request.external_receipt_digests),
                "independent_acceptance_digest": request.independent_acceptance_digest,
                "decision": "CERTIFIED",
                "authority_id": "certification-authority-01",
                "issued_at": 100,
                "expires_at": 300,
                "trust_epoch": 7,
                "key_id": "test-key",
            }
        )

    def test_certification_gate_is_conservative_and_revocation_aware(self) -> None:
        external_digest = DIGEST_A
        acceptance_digest = DIGEST_B
        request = self.certification_request(external_digest, acceptance_digest)
        not_run = evaluate_certification(request, None, verifier=verifier, now=200)
        self.assertEqual(not_run.status, CertificationStatus.NOT_CERTIFIED)
        self.assertIn("NOT_RUN", not_run.blockers[0])

        receipt = self.certification_receipt(request)
        accepted = evaluate_certification(request, receipt, verifier=verifier, now=200)
        self.assertEqual(accepted.status, CertificationStatus.CERTIFIED)
        self.assertEqual(accepted.receipt_digest, receipt["receipt_digest"])

        revoked = evaluate_certification(
            request,
            receipt,
            verifier=verifier,
            revoked_authorities=("certification-authority-01",),
            now=200,
        )
        self.assertEqual(revoked.status, CertificationStatus.NOT_CERTIFIED)
        self.assertIn("revoked", revoked.blockers[0])

        expired = evaluate_certification(request, receipt, verifier=verifier, now=300)
        self.assertEqual(expired.status, CertificationStatus.NOT_CERTIFIED)
        self.assertIn("validity interval", expired.blockers[0])

    def test_bad_external_signatures_never_upgrade_evidence(self) -> None:
        request = self.training_request()
        receipt = self.training_receipt(request)
        receipt["signature"] = "invalid"
        with self.assertRaisesRegex(ExternalAssuranceError, "denied"):
            verify_external_run_receipt(request, receipt, verifier=verifier)

    def test_command_arguments_are_not_interpreted_by_a_shell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "provider"
            marker = Path(directory) / "must-not-exist"
            self.write_provider(executable)
            config = ProviderCommandRoute(
                route_id="route.provider-01",
                route_digest="1" * 64,
                operation="execute",
                provider_id="provider-01",
                provider_version="2026.09",
                executable=executable,
                executable_digest=digest_bytes(executable.read_bytes()),
                arguments=(f";touch {marker}",),
            )
            broker = build_subprocess_broker(
                broker_id="broker.provider-01",
                version="1.0.0",
                routes=(config,),
                receipt_verifier=verifier,
            )
            route, binding, request, permit = self.broker_objects(broker.digest)
            broker.execute(
                route,
                binding,
                request,
                permit,
                {"inputs": {"source": "value"}},
                self.scope,
            )
            self.assertFalse(marker.exists())

    def test_provider_timeout_is_an_unknown_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "slow-provider"
            executable.write_text(
                "#!/usr/bin/env python3\nimport time\ntime.sleep(10)\n",
                encoding="utf-8",
            )
            executable.chmod(0o700)
            config = ProviderCommandRoute(
                route_id="route.provider-01",
                route_digest="1" * 64,
                operation="execute",
                provider_id="provider-01",
                provider_version="2026.09",
                executable=executable,
                executable_digest=digest_bytes(executable.read_bytes()),
                timeout_seconds=0.05,
            )
            broker = build_subprocess_broker(
                broker_id="broker.provider-01",
                version="1.0.0",
                routes=(config,),
                receipt_verifier=verifier,
            )
            route, binding, request, permit = self.broker_objects(broker.digest)
            with self.assertRaisesRegex(ExternalAssuranceError, "unknown outcome"):
                broker.execute(
                    route,
                    binding,
                    request,
                    permit,
                    {"inputs": {"source": "value"}},
                    self.scope,
                )


if __name__ == "__main__":
    unittest.main()
