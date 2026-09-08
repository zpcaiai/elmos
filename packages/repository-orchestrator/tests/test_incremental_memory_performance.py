from __future__ import annotations

import os.path
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from elmos_repository_orchestrator.contracts import ContractError, sha256_payload
from elmos_repository_orchestrator.incremental import (
    BoundedBatchExecutor,
    IncrementalManifest,
    VerifiedArtifactCache,
    analyze_repositories,
)
from elmos_repository_orchestrator.memory import ExperienceMemoryStore, ExperienceRecord, MemoryTier
from elmos_repository_orchestrator.performance import RetrievalCase, benchmark_retrieval, percentile, token_cost
from elmos_repository_orchestrator.retrieval import HybridIndex, RetrievalQuery, SearchDocument, SourceAnchor


def doc(identity: str, content: str, *, modality: str = "text", locator=None) -> SearchDocument:
    return SearchDocument(
        document_id=identity,
        tenant_id="tenant-a",
        project_id="project-a",
        revision_id="rev-1",
        content=content,
        anchor=SourceAnchor(
            f"asset://{identity}",
            f"{modality}-region",
            sha256_payload(content),
            locator=locator or {},
        ),
        allowed_principals=frozenset({"alice"}),
        vector=(1.0, 0.0),
        modality=modality,
    )


class IncrementalPerformanceTests(unittest.TestCase):
    def test_manifest_hashes_only_declared_changes_and_cache_verifies_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.py").write_text("print('a')\n", encoding="utf-8")
            manifest = IncrementalManifest(root)
            first = manifest.update(["a.py"])
            self.assertEqual(len(first.changed), 1)
            second = manifest.update(["a.py"])
            self.assertEqual((len(second.changed), second.unchanged), (0, ("a.py",)))
            (root / "a.py").write_text("print('b')\n", encoding="utf-8")
            third = manifest.update(["a.py"])
            self.assertNotEqual(first.manifest_digest, third.manifest_digest)
            deleted = manifest.update([], ["a.py"])
            self.assertEqual(deleted.deleted, ("a.py",))

            cache = VerifiedArtifactCache(root / "cache.sqlite3")
            cache.put(
                tenant_id="tenant-a",
                project_id="project-a",
                revision_id="rev-1",
                cache_key="graph",
                contract_digest="sha256:" + "a" * 64,
                payload={"nodes": 3},
            )
            self.assertEqual(
                cache.get(
                    tenant_id="tenant-a",
                    project_id="project-a",
                    revision_id="rev-1",
                    cache_key="graph",
                    contract_digest="sha256:" + "a" * 64,
                ),
                {"nodes": 3},
            )
            self.assertIsNone(
                cache.get(
                    tenant_id="tenant-b",
                    project_id="project-a",
                    revision_id="rev-1",
                    cache_key="graph",
                    contract_digest="sha256:" + "a" * 64,
                )
            )
            cache.connection.execute("UPDATE artifact_cache SET payload_json=?", (b'{"nodes":4}',))
            cache.connection.commit()
            with self.assertRaisesRegex(ContractError, "digest mismatch"):
                cache.get(
                    tenant_id="tenant-a",
                    project_id="project-a",
                    revision_id="rev-1",
                    cache_key="graph",
                    contract_digest="sha256:" + "a" * 64,
                )
            cache.close()

    def test_batched_bounded_execution_preserves_order_and_single_repo_avoids_pool(self) -> None:
        calls: list[tuple[int, ...]] = []

        def batch(values):
            calls.append(tuple(values))
            return [value * 2 for value in values]

        result = BoundedBatchExecutor(batch, batch_size=3, max_concurrency=2).run(list(range(8)))
        self.assertEqual(result.items, tuple(value * 2 for value in range(8)))
        self.assertEqual((result.batch_count, result.max_concurrency), (3, 2))
        self.assertEqual(analyze_repositories(["/tmp/repo-a"], os.path.basename), ("repo-a",))
        self.assertEqual(set(analyze_repositories(["/tmp/repo-a", "/tmp/repo-b"], os.path.basename)), {"repo-a", "repo-b"})

    def test_multimodal_filter_anchor_and_benchmark_metrics(self) -> None:
        image = doc("diagram", "queue architecture diagram", modality="image", locator={"page": 2, "x": 0.1, "y": 0.2})
        audio = doc("meeting", "queue discussion", modality="audio", locator={"start_ms": 1000, "end_ms": 3000})
        index = HybridIndex()
        index.upsert([image, audio])
        hits = index.search(
            RetrievalQuery(
                tenant_id="tenant-a",
                project_id="project-a",
                revision_id="rev-1",
                principal_ids=frozenset({"alice"}),
                text="queue",
                vector=(1.0, 0.0),
                modalities=frozenset({"image"}),
            )
        )
        self.assertEqual(hits[0].document.document_id, "diagram")
        self.assertEqual(hits[0].to_payload()["anchor"]["locator"]["page"], 2)
        case = RetrievalCase(
            RetrievalQuery(
                tenant_id="tenant-a",
                project_id="project-a",
                revision_id="rev-1",
                principal_ids=frozenset({"alice"}),
                text="architecture diagram",
                vector=(1.0, 0.0),
                top_k=10,
            ),
            frozenset({"diagram"}),
            {"diagram": 2.0},
        )
        report = benchmark_retrieval([image, audio], [case], repetitions=2, resume_probe=lambda: "checkpoint")
        self.assertEqual(report.recall_at_10, 1.0)
        self.assertGreater(report.ndcg_at_10, 0.0)
        self.assertIsNotNone(report.resume_latency)
        self.assertFalse(report.to_payload()["representative"])
        self.assertEqual(percentile([1, 2, 3], 50), 2)
        self.assertEqual(
            token_cost(
                input_tokens=1000,
                cached_input_tokens=500,
                output_tokens=100,
                input_per_million="2",
                cached_input_per_million="1",
                output_per_million="4",
            ),
            Decimal("0.0019"),
        )


class ExperienceMemoryTests(unittest.TestCase):
    def test_memory_is_scoped_idempotent_and_gold_promotion_is_governed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = ExperienceMemoryStore(Path(temporary) / "memory.sqlite3")
            record = ExperienceRecord(
                record_id="memory-1",
                tenant_id="tenant-a",
                project_id="project-a",
                revision_id="rev-1",
                task_signature="repair durable queue",
                lesson="verify idempotency before retry",
                source_run_id="run-1",
                actor_id="executor-a",
            )
            self.assertTrue(store.put(record))
            self.assertFalse(store.put(record))
            self.assertIsNone(store.get("memory-1", tenant_id="tenant-b", project_id="project-a"))
            self.assertEqual(store.search("queue retry", tenant_id="tenant-a", project_id="project-a"), (record,))
            with self.assertRaisesRegex(ContractError, "must differ"):
                store.promote(
                    "memory-1",
                    tenant_id="tenant-a",
                    project_id="project-a",
                    target_tier=MemoryTier.GOLD,
                    verifier_id="executor-a",
                    accepted_by="reviewer-a",
                    rights_approved=True,
                )
            promoted = store.promote(
                "memory-1",
                tenant_id="tenant-a",
                project_id="project-a",
                target_tier=MemoryTier.GOLD,
                verifier_id="verifier-b",
                accepted_by="reviewer-a",
                rights_approved=True,
                global_training_consent=True,
            )
            self.assertEqual(promoted.tier, MemoryTier.GOLD)
            self.assertEqual(store.global_training_export(tenant_id="tenant-a", project_id="project-a"), (promoted,))
            store.close()


if __name__ == "__main__":
    unittest.main()
