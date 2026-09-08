"""End-to-end tests for externally signed Foundry qualification chains."""

from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
from typing import Any
import unittest

from elmos_foundry.canonical import canonical_digest
from elmos_foundry.domain import CertificationStatus
from elmos_foundry.external_assurance import (
    CertificationRequest,
    ExternalRunKind,
    ExternalRunRequest,
    IndependentAcceptanceRequest,
)
from elmos_foundry.external_qualification import (
    ExternalTrustKey,
    ExternalTrustStore,
    ProviderEvidenceRequest,
    verify_external_qualification_chain,
)


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
KEYS = {
    "provider-01": b"p" * 32,
    "training-provider-01": b"t" * 32,
    "deployment-provider-01": b"d" * 32,
    "independent-verifier-01": b"i" * 32,
    "certification-authority-01": b"c" * 32,
}


class FakeEd25519Backend:
    def verify(self, public_key: bytes, signature: bytes, payload: bytes) -> None:
        if signature != hashlib.sha512(public_key + payload).digest():
            raise ValueError("invalid signature")


class RejectingBackend:
    def verify(self, public_key: bytes, signature: bytes, payload: bytes) -> None:
        raise LookupError("backend rejected the signature")


def signed(authority_id: str, body: dict[str, Any]) -> dict[str, Any]:
    receipt = dict(body)
    receipt["key_id"] = f"{authority_id}-key"
    receipt_digest = canonical_digest(receipt)
    receipt["receipt_digest"] = receipt_digest
    receipt["signature"] = base64.b64encode(
        hashlib.sha512(KEYS[authority_id] + receipt_digest.encode("ascii")).digest()
    ).decode("ascii")
    return receipt


class ExternalQualificationTests(unittest.TestCase):
    def trust_store(
        self,
        *,
        revoke: str | None = None,
        backend: FakeEd25519Backend | RejectingBackend | None = None,
    ) -> ExternalTrustStore:
        roles = {
            "provider-01": ("PROVIDER",),
            "training-provider-01": ("TRAINING_PROVIDER",),
            "deployment-provider-01": ("DEPLOYMENT_PROVIDER",),
            "independent-verifier-01": ("INDEPENDENT_VERIFIER",),
            "certification-authority-01": ("CERTIFICATION_AUTHORITY",),
        }
        return ExternalTrustStore(
            trust_epoch=7,
            keys=tuple(
                ExternalTrustKey(
                    authority_id=authority_id,
                    key_id=f"{authority_id}-key",
                    public_key=key,
                    roles=roles[authority_id],
                    not_before=100,
                    not_after=1000,
                    revoked=authority_id == revoke,
                )
                for authority_id, key in KEYS.items()
            ),
            backend=backend or FakeEd25519Backend(),
        )

    def chain(self) -> dict[str, Any]:
        provider_request = ProviderEvidenceRequest(
            provider_id="provider-01",
            provider_version="2026.09",
            executable_digest=DIGEST_A,
            request_binding_digest=DIGEST_B,
            route_id="route-01",
            route_digest="1" * 64,
            operation="execute",
            outputs_digest=DIGEST_C,
        )
        provider_receipt = signed(
            "provider-01",
            {
                "schema_version": "elmos.foundry.provider-receipt.v1",
                "provider_id": provider_request.provider_id,
                "provider_version": provider_request.provider_version,
                "executable_digest": provider_request.executable_digest,
                "request_binding_digest": provider_request.request_binding_digest,
                "route_id": provider_request.route_id,
                "route_digest": provider_request.route_digest,
                "operation": provider_request.operation,
                "outcome": "CONFIRMED",
                "outputs_digest": provider_request.outputs_digest,
            },
        )
        training_request = ExternalRunRequest(
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
            {"base-model": DIGEST_B, "dataset": DIGEST_C},
            ("lineage", "metrics", "model"),
        )
        training_receipt = signed(
            "training-provider-01",
            {
                "schema_version": "elmos.foundry.external-run-receipt.v1",
                "run_kind": "TRAINING",
                "request_id": training_request.request_id,
                "request_binding_digest": training_request.binding_digest,
                "tenant_id": training_request.tenant_id,
                "project_id": training_request.project_id,
                "target_id": training_request.target_id,
                "environment_id": training_request.environment_id,
                "provider_id": training_request.provider_id,
                "provider_version": training_request.provider_version,
                "executor_id": "trainer-01",
                "outcome": "CONFIRMED",
                "reconciliation_status": "RECONCILED",
                "output_digests": {
                    "lineage": DIGEST_A,
                    "metrics": DIGEST_B,
                    "model": DIGEST_C,
                },
                "started_at": 110,
                "finished_at": 120,
            },
        )
        deployment_request = ExternalRunRequest(
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
        deployment_receipt = signed(
            "deployment-provider-01",
            {
                "schema_version": "elmos.foundry.external-run-receipt.v1",
                "run_kind": "DEPLOYMENT",
                "request_id": deployment_request.request_id,
                "request_binding_digest": deployment_request.binding_digest,
                "tenant_id": deployment_request.tenant_id,
                "project_id": deployment_request.project_id,
                "target_id": deployment_request.target_id,
                "environment_id": deployment_request.environment_id,
                "provider_id": deployment_request.provider_id,
                "provider_version": deployment_request.provider_version,
                "executor_id": "deployer-01",
                "outcome": "CONFIRMED",
                "reconciliation_status": "RECONCILED",
                "output_digests": {
                    "deployment": DIGEST_A,
                    "health": DIGEST_B,
                    "rollback": DIGEST_C,
                },
                "started_at": 130,
                "finished_at": 140,
            },
        )
        external_digests = {
            "DEPLOYMENT": deployment_receipt["receipt_digest"],
            "PROVIDER": provider_receipt["receipt_digest"],
            "TRAINING": training_receipt["receipt_digest"],
        }
        acceptance_request = IndependentAcceptanceRequest(
            "acceptance-request-01",
            "tenant-01",
            "project-01",
            "release-01",
            "producer-01",
            ("deployer-01", "trainer-01"),
            DIGEST_A,
            DIGEST_B,
            external_digests,
            ("E1", "E2", "E3", "E4"),
        )
        acceptance_receipt = signed(
            "independent-verifier-01",
            {
                "schema_version": "elmos.foundry.independent-acceptance-receipt.v1",
                "request_id": acceptance_request.request_id,
                "request_binding_digest": acceptance_request.binding_digest,
                "tenant_id": acceptance_request.tenant_id,
                "project_id": acceptance_request.project_id,
                "target_id": acceptance_request.target_id,
                "evidence_bundle_digest": acceptance_request.evidence_bundle_digest,
                "holdout_corpus_digest": acceptance_request.holdout_corpus_digest,
                "external_receipt_digests": external_digests,
                "verifier_id": "independent-verifier-01",
                "verdict": "PASS",
                "gate_results": {"E1": "PASS", "E2": "PASS", "E3": "PASS", "E4": "PASS"},
                "skipped_cases": [],
                "unknown_cases": [],
            },
        )
        certification_request = CertificationRequest(
            "certification-request-01",
            "tenant-01",
            "project-01",
            "release-01",
            "E4_PRODUCTION_CERTIFIED",
            DIGEST_A,
            DIGEST_B,
            DIGEST_C,
            external_digests,
            acceptance_receipt["receipt_digest"],
            "producer-01",
            ("deployer-01", "trainer-01"),
            "independent-verifier-01",
        )
        certification_receipt = signed(
            "certification-authority-01",
            {
                "schema_version": "elmos.foundry.certification-receipt.v1",
                "request_id": certification_request.request_id,
                "request_binding_digest": certification_request.binding_digest,
                "tenant_id": certification_request.tenant_id,
                "project_id": certification_request.project_id,
                "target_id": certification_request.target_id,
                "certified_level": certification_request.requested_level,
                "catalog_digest": certification_request.catalog_digest,
                "implementation_digest": certification_request.implementation_digest,
                "policy_digest": certification_request.policy_digest,
                "external_receipt_digests": external_digests,
                "independent_acceptance_digest": certification_request.independent_acceptance_digest,
                "decision": "CERTIFIED",
                "authority_id": "certification-authority-01",
                "issued_at": 150,
                "expires_at": 500,
                "trust_epoch": 7,
            },
        )
        return {
            "provider_request": provider_request,
            "provider_receipt": provider_receipt,
            "training_request": training_request,
            "training_receipt": training_receipt,
            "deployment_request": deployment_request,
            "deployment_receipt": deployment_receipt,
            "acceptance_request": acceptance_request,
            "acceptance_receipt": acceptance_receipt,
            "certification_request": certification_request,
            "certification_receipt": certification_receipt,
        }

    def test_complete_external_chain_can_accept_real_authority_receipt(self) -> None:
        decision = verify_external_qualification_chain(
            **self.chain(), trust_store=self.trust_store(), now=200
        )
        self.assertEqual(decision.external_evidence_status, "VERIFIED_INDEPENDENT")
        self.assertEqual(decision.certification_status, CertificationStatus.CERTIFIED)
        self.assertEqual(
            set(decision.receipt_digests),
            {"PROVIDER", "TRAINING", "DEPLOYMENT", "INDEPENDENT_ACCEPTANCE", "CERTIFICATION"},
        )

    def test_independent_and_certification_roles_cannot_share_an_authority(self) -> None:
        with self.assertRaisesRegex(ValueError, "roles must be isolated"):
            ExternalTrustStore(
                trust_epoch=7,
                keys=(
                    ExternalTrustKey(
                        authority_id="combined-authority-01",
                        key_id="combined-key-01",
                        public_key=b"x" * 32,
                        roles=("CERTIFICATION_AUTHORITY", "PROVIDER"),
                        not_before=100,
                        not_after=1000,
                    ),
                ),
                backend=FakeEd25519Backend(),
            )

    def test_chain_rejects_cross_project_requests_before_receipt_verification(self) -> None:
        chain = self.chain()
        chain["training_request"] = replace(
            chain["training_request"], project_id="other-project-01"
        )
        decision = verify_external_qualification_chain(
            **chain, trust_store=self.trust_store(), now=200
        )
        self.assertEqual(decision.external_evidence_status, "REJECTED")
        self.assertIn("cross tenant or project", decision.blockers[0])

    def test_chain_rejects_unbound_external_executor(self) -> None:
        chain = self.chain()
        acceptance = chain["acceptance_request"]
        chain["acceptance_request"] = replace(
            acceptance,
            executor_ids=("deployer-01", "other-executor-01", "trainer-01"),
        )
        chain["certification_request"] = replace(
            chain["certification_request"],
            executor_ids=("deployer-01", "other-executor-01", "trainer-01"),
        )
        decision = verify_external_qualification_chain(
            **chain, trust_store=self.trust_store(), now=200
        )
        self.assertEqual(decision.external_evidence_status, "REJECTED")
        self.assertIn("verified external executors", decision.blockers[0])

    def test_signature_backend_exception_fails_closed(self) -> None:
        decision = verify_external_qualification_chain(
            **self.chain(),
            trust_store=self.trust_store(backend=RejectingBackend()),
            now=200,
        )
        self.assertEqual(decision.external_evidence_status, "REJECTED")
        self.assertEqual(decision.certification_status, CertificationStatus.NOT_CERTIFIED)
        self.assertIn("signature verifier denied", decision.blockers[0])

    def test_missing_certification_stays_not_certified(self) -> None:
        chain = self.chain()
        chain["certification_receipt"] = None
        decision = verify_external_qualification_chain(
            **chain, trust_store=self.trust_store(), now=200
        )
        self.assertEqual(decision.external_evidence_status, "VERIFIED_INDEPENDENT")
        self.assertEqual(decision.certification_status, CertificationStatus.NOT_CERTIFIED)
        self.assertIn("NOT_RUN", decision.blockers[0])

    def test_revoked_provider_and_stale_epoch_fail_closed(self) -> None:
        rejected = verify_external_qualification_chain(
            **self.chain(), trust_store=self.trust_store(revoke="training-provider-01"), now=200
        )
        self.assertEqual(rejected.external_evidence_status, "REJECTED")
        self.assertEqual(rejected.certification_status, CertificationStatus.NOT_CERTIFIED)

        chain = self.chain()
        chain["certification_receipt"]["trust_epoch"] = 6
        rejected = verify_external_qualification_chain(
            **chain, trust_store=self.trust_store(), now=200
        )
        self.assertEqual(rejected.external_evidence_status, "REJECTED")
        self.assertIn("trust epoch", rejected.blockers[0])


if __name__ == "__main__":
    unittest.main()
