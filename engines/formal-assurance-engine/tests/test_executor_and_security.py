from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from elmos_formal_assurance.artifact_store import (
    ArtifactStoreError,
    ContentAddressedArtifactStore,
)
from elmos_formal_assurance.canonical import digest_value
from elmos_formal_assurance.contracts import Scope, TrustedIdentity
from elmos_formal_assurance.executor import LocalEvaluationError
from elmos_formal_assurance.runtime import FormalAssuranceRuntime, RuntimeConfig
from elmos_formal_assurance.store import StateStore, StoreError


def make_scope(
    *,
    tenant: str = "tenant-a",
    project: str = "project-a",
    source: str = "a",
) -> Scope:
    return Scope(
        tenant,
        "account-a",
        project,
        source * 64,
        "b" * 64,
        "c" * 64,
        "local-executor",
    )


class ExecutorAndSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = StateStore()
        self.runtime = FormalAssuranceRuntime(
            store=self.store,
            config=RuntimeConfig(artifact_root=Path(self.temp.name) / "artifacts"),
        )
        self.scope = make_scope()
        self.scope_payload = self.scope.to_dict()
        self.identity = TrustedIdentity("tenant-a", "operator-a", "project-a")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_local_executor_commits_bounded_evidence_and_refutation(self) -> None:
        formula_hash = digest_value("x == x")
        self.store.submit_run(
            self.scope,
            "run-equal",
            "obl-equal",
            formula_hash=formula_hash,
            engine="elmos-local-bounded",
            bound={"scope": 1},
        )
        leased = self.store.lease_run(self.scope, "run-equal", "worker-a", 1)
        self.store.start_run(
            self.scope, "run-equal", "worker-a", leased["fencing_token"]
        )
        result = self.runtime.execute_local_run(
            {
                "scope": self.scope_payload,
                "runId": "run-equal",
                "workerId": "worker-a",
                "token": leased["fencing_token"],
                "assumptionHash": "d" * 64,
                "tcbHash": "e" * 64,
                "evaluation": {
                    "kind": "EXACT_EQUALITY",
                    "expected": {"value": 7},
                    "actual": {"value": 7},
                },
            },
            self.identity,
        )
        self.assertEqual(result["state"], "SUCCEEDED")
        self.assertEqual(result["result"]["status"], "BOUNDED_NO_COUNTEREXAMPLE")
        self.assertEqual(len(result["result"]["artifacts"]), 1)
        artifact = result["result"]["artifacts"][0]
        self.assertEqual(
            self.runtime.artifact_store.metadata("tenant-a", artifact["sha256"])[
                "retentionClass"
            ],
            "AUDIT",
        )

        self.store.submit_run(self.scope, "run-refuted", "obl-refuted")
        leased = self.store.lease_run(self.scope, "run-refuted", "worker-a", 1)
        self.store.start_run(
            self.scope, "run-refuted", "worker-a", leased["fencing_token"]
        )
        refuted = self.runtime.execute_local_run(
            {
                "scope": self.scope_payload,
                "runId": "run-refuted",
                "workerId": "worker-a",
                "token": leased["fencing_token"],
                "assumptionHash": "d" * 64,
                "tcbHash": "e" * 64,
                "evaluation": {
                    "kind": "TRACE_EQUIVALENCE",
                    "sourceTrace": [{"event": "reserved"}],
                    "targetTrace": [{"event": "charged"}],
                },
            },
            self.identity,
        )
        self.assertEqual(
            refuted["result"]["status"], "REFUTED_WITH_COUNTEREXAMPLE"
        )
        self.assertTrue(refuted["result"]["counterexampleId"].startswith("cex-"))

    def test_local_executor_rejects_non_owner_and_non_bounded_mode(self) -> None:
        self.store.submit_run(self.scope, "run-owner", "obl-owner")
        leased = self.store.lease_run(self.scope, "run-owner", "worker-a", 1)
        self.store.start_run(
            self.scope, "run-owner", "worker-a", leased["fencing_token"]
        )
        with self.assertRaises(StoreError):
            self.runtime.local_executor.execute(
                self.scope,
                "run-owner",
                "worker-b",
                leased["fencing_token"],
                {"kind": "EXACT_EQUALITY", "expected": 1, "actual": 1},
                assumption_hash="d" * 64,
                tcb_hash="e" * 64,
            )

        other = make_scope(project="project-a", source="f")
        self.store.submit_run(other, "run-smt", "obl-smt", mode="SMT", engine="z3")
        leased = self.store.lease_run(other, "run-smt", "worker-a", 1)
        self.store.start_run(other, "run-smt", "worker-a", leased["fencing_token"])
        with self.assertRaises(LocalEvaluationError):
            self.runtime.local_executor.execute(
                other,
                "run-smt",
                "worker-a",
                leased["fencing_token"],
                {"kind": "EXACT_EQUALITY", "expected": 1, "actual": 1},
                assumption_hash="d" * 64,
                tcb_hash="e" * 64,
            )

    def test_run_cache_and_documents_are_bound_to_full_scope(self) -> None:
        second_scope = make_scope(project="project-b")
        self.store.submit_run(self.scope, "run-scope", "obl-scope")
        with self.assertRaises(StoreError):
            self.store.get_run(second_scope, "run-scope")
        with self.assertRaises(StoreError):
            self.store.events(second_scope, "proof_run", "run-scope")

        self.store.put_cache(self.scope, "same-key", {"value": "a"})
        self.store.put_cache(second_scope, "same-key", {"value": "b"})
        self.assertEqual(self.store.get_cache(self.scope, "same-key")["value"], "a")
        self.assertEqual(
            self.store.get_cache(second_scope, "same-key")["value"], "b"
        )

        self.store.put_document(
            self.scope, "formal_spec", "spec-a", {"id": "spec-a"}, version="1.0.0"
        )
        with self.assertRaises(StoreError):
            self.store.get_document(
                second_scope, "formal_spec", "spec-a", version="1.0.0"
            )

    def test_concurrency_and_active_owner_limits_fail_closed(self) -> None:
        for index in range(3):
            self.store.submit_run(
                self.scope, f"run-{index}", f"obl-{index}", account_concurrency=3
            )
        with self.assertRaises(StoreError):
            self.store.submit_run(
                self.scope, "run-4", "obl-4", account_concurrency=3
            )

        isolated = make_scope(source="f")
        store = StateStore()
        try:
            store.submit_run(isolated, "run-a", "obl-shared")
            store.lease_run(isolated, "run-a", "worker-a", 1)
            with self.assertRaises(StoreError):
                store.submit_run(isolated, "run-b", "obl-shared")
        finally:
            store.close()

    def test_artifact_paths_are_tenant_safe_and_retention_is_enforced(self) -> None:
        cas = ContentAddressedArtifactStore(Path(self.temp.name) / "cas")
        reference = cas.put(
            "organization/tenant-a",
            b"ephemeral",
            media_type="text/plain",
            retention_class="EPHEMERAL",
        )
        self.assertNotIn("organization", str(next((Path(self.temp.name) / "cas").iterdir())))
        cas.delete(
            "organization/tenant-a",
            reference["sha256"],
            retention_class="EPHEMERAL",
        )
        with self.assertRaises(ArtifactStoreError):
            cas.get("organization/tenant-a", reference["sha256"])

        audit = cas.put(
            "organization/tenant-a",
            b"audit",
            media_type="text/plain",
            retention_class="AUDIT",
        )
        with self.assertRaises(ArtifactStoreError):
            cas.delete("organization/tenant-a", audit["sha256"])


if __name__ == "__main__":
    unittest.main()
