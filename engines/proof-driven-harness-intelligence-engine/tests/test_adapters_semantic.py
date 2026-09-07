from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from elmos_pdhi.adapters import (
    AdapterEvidence,
    AdapterManifest,
    AdapterRegistry,
    AdapterRequest,
    AdapterResult,
    AdapterStatus,
)
from elmos_pdhi.canonical import digest_object
from elmos_pdhi.semantic import (
    PrewalkLimits,
    Provenance,
    SemanticEdge,
    SemanticGraphBuilder,
    SemanticNode,
    SemanticRuntime,
    make_semantic_shard,
    prewalk_repository,
    read_repository_bytes,
)


class _ExactCompilerAdapter:
    manifest = AdapterManifest(
        adapter_id="compiler.fixture",
        protocol="compiler",
        version="1.2.3",
        operations=("symbols",),
        required_authority=("compiler.read",),
        implementation_digest=digest_object({"fixture": "compiler"}, domain="test-fixture"),
    )

    def invoke(self, request: AdapterRequest) -> AdapterResult:
        evidence = AdapterEvidence(
            evidence_id="fixture-evidence",
            artifact_digest=digest_object({"symbols": ["answer"]}, domain="test-fixture"),
            producer=self.manifest.adapter_id,
            tool_version=self.manifest.version,
            input_digest=request.request_digest,
        )
        return AdapterResult(
            status=AdapterStatus.SUCCEEDED,
            request_digest=request.request_digest,
            adapter_id=request.adapter_id,
            protocol=request.protocol,
            operation=request.operation,
            output={"symbols": ["answer"]},
            evidence=(evidence,),
        )


class AdapterSemanticTests(unittest.TestCase):
    def test_missing_adapter_is_not_run_without_implicit_execution(self) -> None:
        request = AdapterRequest(
            request_id="request-1",
            adapter_id="compiler.missing",
            protocol="compiler",
            operation="symbols",
            source_digest=digest_object({"source": 1}, domain="test-fixture"),
        )
        result = AdapterRegistry().invoke(request)
        self.assertEqual(AdapterStatus.NOT_RUN, result.status)
        self.assertFalse(result.usable)
        self.assertFalse(AdapterRegistry().discovery("dap")["network_accessed"])
        self.assertFalse(AdapterRegistry().discovery("dap")["subprocess_started"])

    def test_exact_adapter_requires_protocol_operation_and_authority(self) -> None:
        registry = AdapterRegistry((_ExactCompilerAdapter(),))
        denied = registry.invoke(
            AdapterRequest(
                request_id="request-2",
                adapter_id="compiler.fixture",
                protocol="compiler",
                operation="symbols",
                source_digest=digest_object({"source": 2}, domain="test-fixture"),
            )
        )
        self.assertEqual(AdapterStatus.DENIED, denied.status)
        succeeded = registry.invoke(
            AdapterRequest(
                request_id="request-3",
                adapter_id="compiler.fixture",
                protocol="compiler",
                operation="symbols",
                source_digest=digest_object({"source": 3}, domain="test-fixture"),
                granted_authority=("compiler.read",),
            )
        )
        self.assertEqual(AdapterStatus.SUCCEEDED, succeeded.status)
        self.assertTrue(succeeded.usable)

    def test_prewalk_never_follows_symlinks_and_rejects_traversal(self) -> None:
        with TemporaryDirectory() as repository, TemporaryDirectory() as outside:
            root = Path(repository)
            (root / "src").mkdir()
            (root / "src" / "inside.py").write_text("answer = 42\n", encoding="utf-8")
            secret = Path(outside) / "secret.py"
            secret.write_text("SECRET\n", encoding="utf-8")
            os.symlink(secret, root / "src" / "outside.py")
            result = prewalk_repository(
                root,
                limits=PrewalkLimits(
                    max_files=10,
                    max_total_bytes=1024,
                    max_file_bytes=512,
                    max_depth=5,
                    max_entries=20,
                ),
            )
            self.assertEqual(("src/inside.py",), tuple(item.path for item in result.files))
            self.assertTrue(any("symbolic link" in item.reason for item in result.skipped))
            self.assertEqual(b"answer = 42\n", read_repository_bytes(root, "src/inside.py"))
            with self.assertRaises(ValueError):
                read_repository_bytes(root, "../secret.py")
            with self.assertRaises(OSError):
                read_repository_bytes(root, "src/outside.py")

    def test_incremental_invalidation_propagates_and_unknown_is_explicit(self) -> None:
        with TemporaryDirectory() as repository:
            root = Path(repository)
            (root / "a.py").write_text("def a(): return 1\n", encoding="utf-8")
            (root / "b.py").write_text("from a import a\n", encoding="utf-8")
            first_walk = prewalk_repository(root)
            files = {item.path: item for item in first_walk.files}
            provenance_a = Provenance("fixture-compiler", "a", files["a.py"].digest, "1")
            provenance_b = Provenance("fixture-compiler", "b", files["b.py"].digest, "1")
            node_a = SemanticNode("symbol:a", "definition", "a", "a.py", "python:a", 1.0, False, (provenance_a,))
            node_b = SemanticNode("module:b", "module", "b", "b.py", "python:b", 1.0, False, (provenance_b,))
            reference = SemanticEdge("reference:b-a", "module:b", "symbol:a", "reference", "b.py", 1.0, False, (provenance_b,))
            first = SemanticGraphBuilder().build(
                first_walk,
                {
                    "a.py": make_semantic_shard(files["a.py"], nodes=(node_a,), edges=()),
                    "b.py": make_semantic_shard(files["b.py"], nodes=(node_b,), edges=(reference,), dependencies=("a.py",)),
                },
            )
            self.assertTrue(first.complete)
            self.assertEqual((reference,), SemanticRuntime().semantic_reference_index(first))

            (root / "a.py").write_text("def a(): return 2\n", encoding="utf-8")
            second_walk = prewalk_repository(root)
            second_file = second_walk.file("a.py")
            assert second_file is not None
            provenance_a2 = Provenance("fixture-compiler", "a2", second_file.digest, "1")
            node_a2 = SemanticNode("symbol:a", "definition", "a", "a.py", "python:a", 1.0, False, (provenance_a2,))
            second = SemanticGraphBuilder().build(
                second_walk,
                {"a.py": make_semantic_shard(second_file, nodes=(node_a2,), edges=())},
                previous=first,
            )
            self.assertEqual(("a.py", "b.py"), second.invalidated_paths)
            self.assertFalse(second.complete)
            uncertainty = second.uncertainty()
            self.assertEqual(1, len(uncertainty))
            self.assertTrue(uncertainty[0].unknown)
            self.assertIn("adapter evidence unavailable", uncertainty[0].unknown_reason or "")

    def test_known_unresolved_edge_is_rejected_instead_of_silently_dropped(self) -> None:
        with TemporaryDirectory() as repository:
            root = Path(repository)
            (root / "a.py").write_text("a = 1\n", encoding="utf-8")
            walk = prewalk_repository(root)
            file_record = walk.file("a.py")
            assert file_record is not None
            provenance = Provenance("fixture-compiler", "a", file_record.digest, "1")
            node = SemanticNode("symbol:a", "definition", "a", "a.py", "python:a", 1.0, False, (provenance,))
            bad_edge = SemanticEdge("call:a-missing", "symbol:a", "symbol:missing", "call", "a.py", 1.0, False, (provenance,))
            shard = make_semantic_shard(file_record, nodes=(node,), edges=(bad_edge,))
            with self.assertRaises(ValueError):
                SemanticGraphBuilder().build(walk, {"a.py": shard})

    def test_semantic_shard_digest_is_recomputed_not_caller_authorized(self) -> None:
        with TemporaryDirectory() as repository:
            root = Path(repository)
            (root / "a.py").write_text("a = 1\n", encoding="utf-8")
            walk = prewalk_repository(root)
            file_record = walk.file("a.py")
            assert file_record is not None
            provenance = Provenance("fixture-compiler", "a", file_record.digest, "1")
            node = SemanticNode("symbol:a", "definition", "a", "a.py", "python:a", 1.0, False, (provenance,))
            shard = make_semantic_shard(file_record, nodes=(node,), edges=())
            with self.assertRaises(ValueError):
                replace(shard, shard_digest=digest_object({"forged": True}, domain="test-fixture"))


if __name__ == "__main__":
    unittest.main()
