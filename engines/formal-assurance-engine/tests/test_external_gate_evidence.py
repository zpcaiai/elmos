from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from elmos_formal_assurance.canonical import canonical_json, digest_value
from elmos_formal_assurance.contracts import Scope, TrustedIdentity
from elmos_formal_assurance.gate_evidence import (
    Ed25519GateEvidenceVerifier,
    GateEvidenceError,
)
from elmos_formal_assurance.handlers import HandlerError
from elmos_formal_assurance.runtime import FormalAssuranceRuntime, RuntimeConfig
from elmos_formal_assurance.store import StateStore


class ExternalGateEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.private_key = Ed25519PrivateKey.generate()
        public_key = self.private_key.public_key().public_bytes(
            encoding=Encoding.Raw, format=PublicFormat.Raw
        )
        self.verifier = Ed25519GateEvidenceVerifier({"verifier-key": public_key})
        self.store = StateStore()
        self.runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(gate_evidence_verifier=self.verifier),
        )
        self.identity = TrustedIdentity(
            "tenant-a", "operator-a", "project-a", ("formal-assurance-control",)
        )
        self.scope = Scope(
            "tenant-a",
            "account-a",
            "project-a",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "golden-route",
        )
        formula_hash = digest_value("P")
        self.payload = {
            "scope": self.scope.to_dict(),
            "subjectId": "release-subject",
            "idempotencyKey": "gate-no-receipt",
            "requiredGate": "E5_CUSTOMER_GOLDEN_ROUTE",
            "policyRevision": "policy-v1",
            "obligations": [
                {
                    "id": "obligation-release",
                    "criticality": "P1",
                    "propertyKind": "FUNCTIONAL_CORRECTNESS",
                    "requiredAssurance": "A2_SOLVER_PROVED",
                    "formula": "P",
                    "formulaHash": formula_hash,
                }
            ],
            "results": [
                {
                    "runId": "run-release",
                    "obligationId": "obligation-release",
                    "status": "PROVED_SOLVER_TRUSTED",
                    "assuranceLevel": "A2_SOLVER_PROVED",
                    "engine": "smt",
                    "mode": "SMT",
                    "assumptionHash": digest_value("assumptions"),
                    "tcbHash": digest_value("tcb"),
                    "formulaHash": formula_hash,
                }
            ],
        }

    def tearDown(self) -> None:
        self.store.close()

    def _receipt(self, decision_input_digest: str) -> dict[str, object]:
        issued_at = (self.now - timedelta(minutes=1)).isoformat().replace(
            "+00:00", "Z"
        )
        expires_at = (self.now + timedelta(minutes=10)).isoformat().replace(
            "+00:00", "Z"
        )
        unsigned = {
            "format": "elmos-formal-external-gate-evidence/v1",
            "receiptId": "receipt-golden-route",
            "scopeDigest": digest_value(self.scope.to_dict()),
            "subjectId": "release-subject",
            "gate": "E5_CUSTOMER_GOLDEN_ROUTE",
            "decisionInputDigest": decision_input_digest,
            "evidenceDigest": digest_value("golden-route-evidence"),
            "deploymentComplete": True,
            "externalEvidenceComplete": True,
            "executorId": "deployment-executor",
            "independentVerifierId": "independent-verifier",
            "issuedAt": issued_at,
            "expiresAt": expires_at,
            "keyId": "verifier-key",
            "signatureAlgorithm": "ED25519",
        }
        return {
            **unsigned,
            "signature": base64.b64encode(
                self.private_key.sign(canonical_json(unsigned))
            ).decode("ascii"),
        }

    def test_unsigned_gate_defaults_to_not_run_and_denies(self) -> None:
        result = self.runtime.dispatch(
            "elmos-formal-release-gate", self.payload, self.identity
        )
        self.assertEqual(result["output"]["gateDecision"]["decision"], "DENY")
        self.assertEqual(
            result["output"]["gateEvidenceVerification"]["verificationStatus"],
            "NOT_RUN",
        )
        self.assertEqual(result["output"]["certification"], "NOT_CERTIFIED")

    def test_signed_external_receipt_is_bound_to_the_decision(self) -> None:
        first = self.runtime.dispatch(
            "elmos-formal-release-gate", self.payload, self.identity
        )
        accepted_payload = {
            **self.payload,
            "idempotencyKey": "gate-signed-receipt",
            "gateEvidenceReceipt": self._receipt(
                first["output"]["decisionInputDigest"]
            ),
        }
        result = self.runtime.dispatch(
            "elmos-formal-release-gate", accepted_payload, self.identity
        )
        self.assertEqual(result["output"]["gateDecision"]["decision"], "ALLOW")
        self.assertEqual(
            result["output"]["gateEvidenceVerification"]["verificationStatus"],
            "INDEPENDENT_EXTERNAL_VERIFIED",
        )
        self.assertEqual(
            result["output"]["gateDocument"]["gateEvidence"]["externalEvidenceComplete"],
            True,
        )
        self.assertEqual(result["output"]["certification"], "NOT_CERTIFIED")
        self.assertEqual(
            result["externalEvidenceStatus"], "INDEPENDENT_EXTERNAL_VERIFIED"
        )

    def test_boolean_completion_claim_without_receipt_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            HandlerError, "cannot be asserted without matching signed evidence"
        ):
            self.runtime.dispatch(
                "elmos-formal-release-gate",
                {**self.payload, "externalEvidenceComplete": True},
                self.identity,
            )

    def test_cross_scope_receipt_is_rejected(self) -> None:
        receipt = self._receipt(digest_value({"decision": "input"}))
        other_scope = Scope(
            "tenant-b",
            "account-b",
            "project-b",
            "a" * 64,
            "b" * 64,
            "c" * 64,
            "golden-route",
        )
        with self.assertRaises(GateEvidenceError):
            self.verifier.verify(
                receipt,
                scope=other_scope,
                subject_id="release-subject",
                gate="E5_CUSTOMER_GOLDEN_ROUTE",
                decision_input_digest=digest_value({"decision": "input"}),
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
