from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from elmos_proof_harness.architecture import (
    ArchitectureDiff,
    ArchitectureEdge,
    ArchitectureGraph,
    ArchitectureNode,
    ArchitectureNodeKind,
)
from elmos_proof_harness.repository import (
    RepositorySnapshotter,
    SnapshotLimitError,
    SnapshotLimits,
    SnapshotRaceError,
    UnsafeRepositoryPath,
)
from elmos_proof_harness.semantic import (
    FRAMEWORK_PROFILES,
    LANGUAGE_PROFILES,
    CapabilityState,
    SemanticCompiler,
    analyze_semantic_gaps,
)


class RepositorySnapshotTests(unittest.TestCase):
    def test_snapshot_is_byte_bound_and_skips_unsafe_or_generated_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "pkg").mkdir()
            (root / "pkg" / "main.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
            (root / "asset.bin").write_bytes(b"\x00\x01\x02")
            (root / "generated").mkdir()
            (root / "generated" / "model.py").write_text("bad = True\n", encoding="utf-8")
            (root / "vendor").mkdir()
            (root / "vendor" / "vendored.py").write_text("bad = True\n", encoding="utf-8")
            outside = root.parent / f"{root.name}-outside.txt"
            outside.write_text("outside", encoding="utf-8")
            try:
                (root / "escape").symlink_to(outside)
                graph = RepositorySnapshotter(root).snapshot()
            finally:
                outside.unlink(missing_ok=True)

            self.assertFalse(graph.complete)
            self.assertTrue(graph.declared_scope_complete)
            self.assertFalse(graph.whole_repository_complete)
            self.assertEqual([item.path for item in graph.files], ["asset.bin", "pkg/main.py"])
            self.assertTrue(graph.file("asset.bin").binary)  # type: ignore[union-attr]
            self.assertEqual(graph.file("pkg/main.py").text(), "def answer():\n    return 42\n")  # type: ignore[union-attr]
            omissions = {(item.path, item.reason) for item in graph.omissions}
            self.assertIn(("generated", "generated"), omissions)
            self.assertIn(("vendor", "vendor"), omissions)
            self.assertIn(("escape", "symlink"), omissions)
            self.assertFalse(graph.provenance["executed_repository_code"])
            self.assertEqual(graph.snapshot_id, RepositorySnapshotter(root).snapshot().snapshot_id)

    def test_limits_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "large.py").write_bytes(b"x" * 32)
            with self.assertRaises(SnapshotLimitError):
                RepositorySnapshotter(root, limits=SnapshotLimits(max_file_bytes=16)).snapshot()

    def test_gitignore_symlink_and_casefold_collision_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / f"{root.name}-ignore"
            outside.write_text("*.py\n", encoding="utf-8")
            try:
                (root / ".gitignore").symlink_to(outside)
                with self.assertRaises(UnsafeRepositoryPath):
                    RepositorySnapshotter(root).snapshot()
            finally:
                outside.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Case.py").write_text("x = 1\n", encoding="utf-8")

            class FakeEntry:
                def __init__(self, name: str) -> None:
                    self.name = name

                def stat(self, *, follow_symlinks: bool = False):
                    self.assert_no_follow = follow_symlinks
                    return (root / "Case.py").lstat()

            with patch(
                "elmos_proof_harness.repository.os.scandir",
                return_value=[FakeEntry("Case.py"), FakeEntry("case.py")],
            ):
                with self.assertRaises(UnsafeRepositoryPath):
                    RepositorySnapshotter(root).snapshot()

    def test_root_change_during_snapshot_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "main.py").write_text("x = 1\n", encoding="utf-8")
            from elmos_proof_harness import repository as repository_module

            original = repository_module._read_stable_file_at
            changed = False

            def mutate(directory_fd, name, relative, limit, expected):
                nonlocal changed
                result = original(directory_fd, name, relative, limit, expected)
                if relative == "main.py" and not changed:
                    changed = True
                    (root / "late.py").write_text("late = True\n", encoding="utf-8")
                return result

            with patch(
                "elmos_proof_harness.repository._read_stable_file_at",
                side_effect=mutate,
            ):
                with self.assertRaises(SnapshotRaceError):
                    RepositorySnapshotter(root).snapshot()

    def test_deep_parent_binding_swap_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            parent = root / "a" / "b"
            parent.mkdir(parents=True)
            (parent / "main.py").write_text("x = 1\n", encoding="utf-8")
            from elmos_proof_harness import repository as repository_module

            original = repository_module._read_stable_file_at
            changed = False

            def swap(directory_fd, name, relative, limit, expected):
                nonlocal changed
                result = original(directory_fd, name, relative, limit, expected)
                if relative == "a/b/main.py" and not changed:
                    changed = True
                    parent.rename(root / "a" / "b-original")
                    parent.mkdir()
                    (parent / "main.py").write_text(
                        "attacker = True\n", encoding="utf-8"
                    )
                return result

            with patch(
                "elmos_proof_harness.repository._read_stable_file_at",
                side_effect=swap,
            ):
                with self.assertRaises(SnapshotRaceError):
                    RepositorySnapshotter(root).snapshot()

    def test_ignore_policy_change_after_read_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ignore = root / ".gitignore"
            ignore.write_text("*.tmp\n", encoding="utf-8")
            (root / "main.py").write_text("x = 1\n", encoding="utf-8")
            from elmos_proof_harness import repository as repository_module

            original = repository_module._read_stable_file_at

            def mutate(directory_fd, name, relative, limit, expected):
                result = original(directory_fd, name, relative, limit, expected)
                if relative == "main.py":
                    ignore.write_text("*.py\n", encoding="utf-8")
                return result

            with patch(
                "elmos_proof_harness.repository._read_stable_file_at",
                side_effect=mutate,
            ):
                with self.assertRaises(SnapshotRaceError):
                    RepositorySnapshotter(root).snapshot()


class SemanticCompilerTests(unittest.TestCase):
    def test_profiles_and_explicit_capabilities(self) -> None:
        self.assertEqual(len(LANGUAGE_PROFILES), 15)
        self.assertEqual(len(FRAMEWORK_PROFILES), 9)
        capabilities = {item.language: item for item in SemanticCompiler().capabilities()}
        self.assertTrue(capabilities["python"].authoritative)
        self.assertEqual(capabilities["java"].state, CapabilityState.UNSUPPORTED)
        self.assertFalse(capabilities["sql"].authoritative)

    def test_python_ast_is_authoritative_and_java_is_not_faked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app.py").write_text(
                "import json\n\nclass App:\n    async def run(self, value: int):\n        return await value\n",
                encoding="utf-8",
            )
            (root / "App.java").write_text("class App { int x; }\n", encoding="utf-8")
            graph = RepositorySnapshotter(root).snapshot()
            bundle = SemanticCompiler().compile(graph)
            python = bundle.shard("app.py")
            java = bundle.shard("App.java")
            self.assertIsNotNone(python)
            self.assertTrue(python.authoritative)  # type: ignore[union-attr]
            self.assertIn("class", {node.kind for node in python.nodes})  # type: ignore[union-attr]
            self.assertIn("async-function", {node.kind for node in python.nodes})  # type: ignore[union-attr]
            self.assertTrue(all(entry.source_digest == graph.file("app.py").digest for entry in python.source_map))  # type: ignore[union-attr]
            self.assertEqual(java.capability.state, CapabilityState.UNSUPPORTED)  # type: ignore[union-attr]
            self.assertFalse(java.authoritative)  # type: ignore[union-attr]
            self.assertEqual(java.gaps[0].family, "frontend-unavailable")  # type: ignore[union-attr]
            self.assertFalse(bundle.completeness["complete"])

    def test_duplicate_json_is_a_blocking_semantic_gap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config.json").write_text('{"a": 1, "a": 2}\n', encoding="utf-8")
            shard = SemanticCompiler().compile(RepositorySnapshotter(root).snapshot()).shard("config.json")
            self.assertFalse(shard.authoritative)  # type: ignore[union-attr]
            self.assertEqual(shard.gaps[0].family, "duplicate-key")  # type: ignore[union-attr]
            self.assertEqual(shard.gaps[0].policy, "BLOCK")  # type: ignore[union-attr]

    def test_yaml_duplicate_is_partial_or_explicitly_unsupported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config.yaml").write_text("a: 1\na: 2\n", encoding="utf-8")
            bundle = SemanticCompiler().compile(RepositorySnapshotter(root).snapshot())
            shard = bundle.shard("config.yaml")
            self.assertIsNotNone(shard)
            self.assertFalse(shard.authoritative)  # type: ignore[union-attr]
            self.assertFalse(bundle.completeness["complete"])
            self.assertIn(
                shard.capability.state,  # type: ignore[union-attr]
                {CapabilityState.PARTIAL, CapabilityState.UNSUPPORTED},
            )

    def test_dependency_fingerprint_invalidates_reverse_cone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "a.py").write_text("import b\nVALUE = b.VALUE\n", encoding="utf-8")
            (root / "b.py").write_text("VALUE = 1\n", encoding="utf-8")
            compiler = SemanticCompiler()
            first = compiler.compile(RepositorySnapshotter(root).snapshot())
            (root / "b.py").write_text("VALUE = 2\n", encoding="utf-8")
            second = compiler.compile(RepositorySnapshotter(root).snapshot(), previous=first)
            self.assertEqual(set(second.invalidated_paths), {"a.py", "b.py"})
            self.assertFalse(second.reused_paths)
            self.assertNotEqual(first.shard("a.py").dependency_fingerprint, second.shard("a.py").dependency_fingerprint)  # type: ignore[union-attr]

    def test_cross_profile_gap_generation_is_deterministic(self) -> None:
        first = analyze_semantic_gaps("python", "java")
        second = analyze_semantic_gaps("python", "java")
        self.assertEqual(first, second)
        self.assertIn("numeric", {item.family for item in first})
        self.assertTrue(all(item.policy in {"BLOCK", "REVIEW"} for item in first))


class ArchitectureTests(unittest.TestCase):
    def test_exports_diff_and_impact_are_deterministic(self) -> None:
        module = ArchitectureNode("m", ArchitectureNodeKind.MODULE, "module", authoritative=True)
        service = ArchitectureNode("s", ArchitectureNodeKind.SERVICE, "service")
        database = ArchitectureNode("d", ArchitectureNodeKind.DATABASE, "db")
        before = ArchitectureGraph.create("snap-1", (module, service), (ArchitectureEdge("m", "s", "defines"),))
        after = ArchitectureGraph.create("snap-2", (module, service, database), (ArchitectureEdge("m", "s", "defines"), ArchitectureEdge("s", "d", "uses")))
        self.assertEqual(json.loads(before.to_json()), before.to_dict())
        self.assertEqual(before.to_calm(), before.to_calm())
        self.assertEqual(before.graph_rows(), before.graph_rows())
        self.assertEqual(after.impact(("d",), direction="upstream"), ("d", "m", "s"))
        diff = ArchitectureDiff.compare(before, after)
        self.assertEqual([item.id for item in diff.added_nodes], ["d"])
        self.assertEqual(diff.impacted_after, ("d", "m", "s"))


if __name__ == "__main__":
    unittest.main()
