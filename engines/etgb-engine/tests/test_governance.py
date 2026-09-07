from __future__ import annotations

import base64
import datetime as dt
import unittest
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from elmos_etgb.attestation import unsigned_payload
from elmos_etgb.canonical import canonical_json
from elmos_etgb.governance import ROLE_NAMES, campaign_context_from_results, verify_release_governance


class ReleaseGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.keys = {
            "approval-key": Ed25519PrivateKey.generate(),
            "production-key": Ed25519PrivateKey.generate(),
        }
        self.trust_store = {
            "schema_version": "1.0",
            "keys": [
                self._trust_key("approval-key", "role-assignment"),
                self._trust_key("production-key", "production-authorization"),
            ],
        }
        self.binding = {
            "candidate_digest": "sha256:" + "a" * 64,
            "plan_digest": "sha256:" + "b" * 64,
            "tenant_id": "tenant-a",
            "project_id": "project-a",
            "task_id": "campaign-a",
            "environment_id": "production-a",
            "authority_id": "authority-a",
        }
        self.roles = {
            "release_owner": ["release-owner-1"],
            "code_owner": ["code-owner-1"],
            "harness_administrator": ["harness-admin-1"],
            "harness_executor": ["executor-1", "worker-1"],
            "corpus_license_reviewer": ["license-reviewer-1"],
            "qa_reviewer": ["qa-reviewer-1"],
            "security_reviewer": ["security-reviewer-1"],
            "independent_approver": ["approver-1"],
            "independent_verifier": ["verifier-1"],
            "production_environment_owner": ["production-owner-1"],
            "external_certification_authority": ["certification-authority-1"],
        }
        self.assertEqual(set(self.roles), set(ROLE_NAMES))

    def _trust_key(self, key_id: str, record_type: str) -> dict[str, Any]:
        public = self.keys[key_id].public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        )
        return {
            "key_id": key_id,
            "algorithm": "ed25519",
            "status": "active",
            "record_types": [record_type],
            "public_key": base64.urlsafe_b64encode(public).decode().rstrip("="),
            "not_before": (self.now - dt.timedelta(hours=1)).isoformat(),
            "not_after": (self.now + dt.timedelta(hours=2)).isoformat(),
        }

    def _record(self, record_type: str, payload: dict[str, Any], *, issuer_id: str, key_id: str) -> dict[str, Any]:
        record = {
            "schema_version": "1.0",
            "record_type": record_type,
            "payload": payload,
            "issuer_id": issuer_id,
            "key_id": key_id,
            "algorithm": "ed25519",
            "issued_at": (self.now - dt.timedelta(minutes=1)).isoformat(),
            "expires_at": (self.now + dt.timedelta(hours=1)).isoformat(),
        }
        signature = self.keys[key_id].sign(canonical_json(unsigned_payload(record)))
        record["signature"] = base64.urlsafe_b64encode(signature).decode().rstrip("=")
        return record

    def _records(self, *, roles: dict[str, list[str]] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        role_record = self._record(
            "role-assignment",
            {
                "schema_version": "1.0",
                "candidate_digest": self.binding["candidate_digest"],
                "plan_digest": self.binding["plan_digest"],
                "tenant_id": self.binding["tenant_id"],
                "project_id": self.binding["project_id"],
                "task_id": self.binding["task_id"],
                "status": "approved",
                "roles": roles or self.roles,
            },
            issuer_id="approver-1",
            key_id="approval-key",
        )
        authority_record = self._record(
            "production-authorization",
            {
                "schema_version": "1.0",
                **self.binding,
                "status": "approved",
                "authorized_executor_ids": ["executor-1", "worker-1"],
                "allowed_effects": ["external-case-execution", "cleanup", "rollback"],
                "cleanup_required": True,
                "rollback_required": True,
            },
            issuer_id="production-owner-1",
            key_id="production-key",
        )
        return role_record, authority_record

    def _verify(self, role_record: dict[str, Any] | None, authority_record: dict[str, Any] | None) -> dict[str, Any]:
        return verify_release_governance(
            role_assignment=role_record,
            production_authority=authority_record,
            trust_store=self.trust_store,
            **self.binding,
            executor_ids=["executor-1"],
            owner_ids=["worker-1"],
            verifier_id="verifier-1",
        )

    def test_signed_exact_governance_is_verified(self) -> None:
        result = self._verify(*self._records())
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["certification_status"], "NOT_CERTIFIED")

    def test_role_overlap_and_unsigned_placeholders_fail_closed(self) -> None:
        roles = {name: list(values) for name, values in self.roles.items()}
        roles["independent_verifier"] = ["executor-1"]
        result = self._verify(*self._records(roles=roles))
        self.assertFalse(result["valid"])
        self.assertTrue(any("role separation violated" in error for error in result["errors"]))
        missing = self._verify(None, None)
        self.assertFalse(missing["valid"])
        self.assertTrue(any("signed role-assignment" in error for error in missing["errors"]))

    def test_campaign_binding_and_executor_identity_are_recovered_exactly(self) -> None:
        binding = {**self.binding, "owner_id": "worker-1"}
        results = [
            {
                "evidence": {
                    "adapter": "external-transformation-harness",
                    "campaign_binding": binding,
                    "signed_response": {"issuer_id": "executor-1"},
                }
            },
            {"evidence": {"adapter": "local-process", "campaign_binding": binding}},
        ]
        context = campaign_context_from_results(results)
        self.assertTrue(context["valid"], context["errors"])
        self.assertEqual(context["executor_ids"], ["executor-1"])
        self.assertEqual(context["owner_ids"], ["worker-1"])


if __name__ == "__main__":
    unittest.main()
