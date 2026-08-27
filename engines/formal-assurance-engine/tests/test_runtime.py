from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from elmos_formal_assurance.artifact_store import ArtifactStoreError
from elmos_formal_assurance.contracts import TrustedIdentity
from elmos_formal_assurance.runtime import (
    FormalAssuranceRuntime,
    RuntimeAuthorizationError,
    RuntimeConfig,
)
from elmos_formal_assurance.store import StateStore, StoreError


def scope(tenant: str = "tenant-a", project: str = "project-a") -> dict[str, object]:
    return {
        "tenantId": tenant,
        "accountId": "account-a",
        "projectId": project,
        "sourceArtifactDigest": "a" * 64,
        "targetArtifactDigest": "b" * 64,
        "environmentDigest": "c" * 64,
        "workloadKey": "local-replay",
    }


class RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = StateStore()
        self.runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(artifact_root=Path(self.temp.name) / "artifacts"),
        )
        self.identity = TrustedIdentity("tenant-a", "operator-a", "project-a")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def dispatch(
        self, skill_id: str, payload: dict[str, object], key: str = "request-1"
    ) -> dict[str, object]:
        return self.runtime.dispatch(
            skill_id,
            {
                "scope": scope(),
                "subjectId": "subject-a",
                "idempotencyKey": key,
                **payload,
            },
            self.identity,
        )

    def test_registry_has_exactly_sixty_explicit_bindings(self) -> None:
        records = self.runtime.list_skills()
        self.assertEqual(len(records), 60)
        self.assertEqual(len({record["skillId"] for record in records}), 60)
        self.assertEqual(len({record["handlerId"] for record in records}), 60)
        self.assertTrue(
            all(
                record["implementationState"] == "BOUND_LOCAL_EXACT"
                for record in records
            )
        )

    def test_dispatch_is_idempotent_and_request_bound(self) -> None:
        payload = {
            "formalSpec": {
                "id": "spec-1",
                "tenant": {"tenantId": "tenant-a", "accountId": "account-a"},
                "businessLine": "core",
                "specKind": "FUNCTION",
                "version": "1.0.0",
                "sourceHash": "d" * 64,
                "semanticProfile": "python-3.12",
                "status": "FROZEN",
                "body": {"postcondition": "x >= 0"},
                "provenance": {
                    "sourceType": "test",
                    "sourceRevision": "r1",
                    "capturedAt": "2026-08-27T00:00:00Z",
                },
            }
        }
        first = self.dispatch("elmos-formal-spec-ir", payload)
        replay = self.dispatch("elmos-formal-spec-ir", payload)
        self.assertEqual(first, replay)
        with self.assertRaises(StoreError):
            self.dispatch(
                "elmos-formal-spec-ir",
                {
                    **payload,
                    "formalSpec": {**payload["formalSpec"], "version": "1.0.1"},
                },
                "request-1",
            )

    def test_trusted_identity_is_required_for_tenant_scope(self) -> None:
        with self.assertRaises(RuntimeAuthorizationError):
            self.runtime.dispatch(
                "elmos-formal-spec-ir",
                {
                    "scope": scope("tenant-b"),
                    "subjectId": "subject-a",
                    "idempotencyKey": "key-b",
                    "formalSpec": {},
                },
                self.identity,
            )

    def test_artifact_is_stored_and_cross_tenant_read_is_denied(self) -> None:
        result = self.dispatch(
            "elmos-proof-artifact-store",
            {"artifactContent": "immutable evidence"},
            "artifact-1",
        )
        artifact = result["output"]["artifact"]
        self.assertTrue(result["output"]["storedInLocalCas"])
        self.assertEqual(
            self.runtime.artifact_store.get("tenant-a", artifact["sha256"]),
            b"immutable evidence",
        )
        with self.assertRaises(ArtifactStoreError):
            self.runtime.artifact_store.get("tenant-b", artifact["sha256"])

    def test_unsafe_dynamic_sql_is_refuted(self) -> None:
        result = self.dispatch(
            "elmos-dynamic-sql-proof-boundary",
            {
                "templates": ["select * from users where id = ${id}"],
                "enumerationBound": 10,
            },
            "sql-1",
        )
        self.assertEqual(result["proofStatus"], "REFUTED_WITH_COUNTEREXAMPLE")
        self.assertEqual(result["assuranceLevel"], "NONE")


if __name__ == "__main__":
    unittest.main()
