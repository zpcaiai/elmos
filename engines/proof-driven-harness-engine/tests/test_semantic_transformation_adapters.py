from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import textwrap
import threading
import unittest
from unittest.mock import patch

from elmos_proof_harness.adapters import (
    DECLARED_ADAPTER_REGISTRY,
    HARNESS_ADAPTER_REGISTRY,
    VERIFIER_ADAPTER_REGISTRY,
    AdapterInvocation,
    AdapterManifest,
    AdapterRegistry,
    AdapterStatus,
)
from elmos_proof_harness.transformation import (
    ChangeSet,
    FileChange,
    TransformationConflict,
    UnsafeTransformationPath,
    WorkspaceTransformer,
)


class TransformationTests(unittest.TestCase):
    def test_dry_run_apply_and_rollback_are_digest_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "src" / "value.txt"
            target.parent.mkdir()
            target.write_text("before\n", encoding="utf-8")
            expected = hashlib.sha256(b"before\n").hexdigest()
            change_set = ChangeSet((FileChange.text("src/value.txt", "after\n", expected_digest=expected),), "test change", "request-1")
            transformer = WorkspaceTransformer(root)
            plan = transformer.plan(change_set)
            self.assertEqual(target.read_text(), "before\n")
            self.assertIn("-before", plan.changes[0].patch)
            self.assertIn("+after", plan.changes[0].patch)
            receipt = transformer.apply(change_set)
            self.assertEqual(target.read_text(), "after\n")
            rolled_back = transformer.rollback(receipt)
            self.assertTrue(rolled_back.rolled_back)
            self.assertEqual(target.read_text(), "before\n")

    def test_conflict_and_symlink_escape_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "value.txt").write_text("current", encoding="utf-8")
            transformer = WorkspaceTransformer(root)
            bad = ChangeSet((FileChange.text("value.txt", "next", expected_digest="0" * 64),), "conflict", "request-2")
            with self.assertRaises(TransformationConflict):
                transformer.apply(bad)
            outside = root.parent / f"{root.name}-outside"
            outside.mkdir()
            try:
                (root / "link").symlink_to(outside, target_is_directory=True)
                escaped = ChangeSet((FileChange.text("link/new.txt", "bad", expected_digest=None),), "escape", "request-3")
                with self.assertRaises(UnsafeTransformationPath):
                    transformer.plan(escaped)
                self.assertFalse((outside / "new.txt").exists())
            finally:
                outside.rmdir()

    def test_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(UnsafeTransformationPath):
            FileChange.text("../escape", "bad", expected_digest=None)

    def test_parent_symlink_and_target_inode_swaps_fail_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root.parent / f"{root.name}-outside"
            outside.mkdir()
            parent = root / "src"
            parent.mkdir()
            target = parent / "value.txt"
            target.write_text("before", encoding="utf-8")
            change = ChangeSet(
                (
                    FileChange.text(
                        "src/value.txt",
                        "after",
                        expected_digest=hashlib.sha256(b"before").hexdigest(),
                    ),
                ),
                "race",
                "request-race-parent",
            )
            transformer = WorkspaceTransformer(root)
            original_binding = transformer._parent_binding_matches
            swapped = False

            def swap_parent(root_fd, relative, expected):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    parent.rename(root / "src-original")
                    parent.symlink_to(outside, target_is_directory=True)
                return original_binding(root_fd, relative, expected)

            try:
                with patch.object(
                    transformer,
                    "_parent_binding_matches",
                    side_effect=swap_parent,
                ):
                    with self.assertRaises(TransformationConflict):
                        transformer.apply(change)
                self.assertFalse((outside / "value.txt").exists())
            finally:
                if parent.is_symlink():
                    parent.unlink()
                outside.rmdir()

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "value.txt"
            target.write_text("before", encoding="utf-8")
            change = ChangeSet(
                (
                    FileChange.text(
                        "value.txt",
                        "after",
                        expected_digest=hashlib.sha256(b"before").hexdigest(),
                    ),
                ),
                "race",
                "request-race-target",
            )
            transformer = WorkspaceTransformer(root)
            original_verify = transformer._verify_target_identity
            swapped = False

            def swap_target(parent_fd, leaf, expected, display_path):
                nonlocal swapped
                if not swapped:
                    swapped = True
                    target.rename(root / "value-original.txt")
                    target.write_text("attacker", encoding="utf-8")
                return original_verify(parent_fd, leaf, expected, display_path)

            with patch.object(
                transformer,
                "_verify_target_identity",
                side_effect=swap_target,
            ):
                with self.assertRaises(TransformationConflict):
                    transformer.apply(change)
            self.assertEqual(target.read_text(encoding="utf-8"), "attacker")

    def test_rollback_rejects_concurrently_replaced_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "value.txt"
            target.write_text("before", encoding="utf-8")
            transformer = WorkspaceTransformer(root)
            change = ChangeSet(
                (
                    FileChange.text(
                        "value.txt",
                        "after",
                        expected_digest=hashlib.sha256(b"before").hexdigest(),
                    ),
                ),
                "rollback race",
                "request-rollback-race",
            )
            receipt = transformer.apply(change)
            target.rename(root / "after-original.txt")
            target.write_text("attacker", encoding="utf-8")
            with self.assertRaises(TransformationConflict):
                transformer.rollback(receipt)
            self.assertEqual(target.read_text(encoding="utf-8"), "attacker")


class AdapterTests(unittest.TestCase):
    def test_exact_source_adapter_descriptors_are_declared_not_run(self) -> None:
        expected_verifiers = {
            "verifier-alive2",
            "verifier-alloy",
            "verifier-apalache",
            "verifier-boogie",
            "verifier-cbmc",
            "verifier-cvc5-smt",
            "verifier-dafny",
            "verifier-differential-runtime",
            "verifier-frama-c",
            "verifier-java-pathfinder",
            "verifier-kani",
            "verifier-key-java",
            "verifier-lean-proof-checker",
            "verifier-openjml",
            "verifier-property-fuzz-mutation",
            "verifier-security-performance-resilience",
            "verifier-sqlsolver",
            "verifier-tla-tlc",
            "verifier-verieql",
            "verifier-z3-smt",
        }
        expected_harnesses = {
            "harness-claude-code",
            "harness-codex-app-server",
            "harness-mcp-a2a",
            "harness-opencode",
            "harness-openhands",
            "harness-openharness",
            "harness-symphony",
        }
        self.assertEqual(set(VERIFIER_ADAPTER_REGISTRY), expected_verifiers)
        self.assertEqual(set(HARNESS_ADAPTER_REGISTRY), expected_harnesses)
        self.assertEqual(len(DECLARED_ADAPTER_REGISTRY), 27)
        self.assertEqual(
            set(DECLARED_ADAPTER_REGISTRY), expected_verifiers | expected_harnesses
        )
        for adapter_id, descriptor in DECLARED_ADAPTER_REGISTRY.items():
            self.assertEqual(descriptor.adapter_id, adapter_id)
            self.assertTrue(descriptor.capabilities)
            self.assertTrue(descriptor.required_authority)
            self.assertEqual(descriptor.implementation_state, "ADAPTER_REQUIRED")
            self.assertEqual(descriptor.runtime_status, "NOT_RUN")
            self.assertFalse(descriptor.to_dict()["sourceConfigurationExecuted"])

    def _adapter(self, root: Path, body: str) -> AdapterManifest:
        executable = root / "adapter"
        executable.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body), encoding="utf-8")
        executable.chmod(0o755)
        digest = hashlib.sha256(executable.read_bytes()).hexdigest()
        return AdapterManifest("test-adapter", "1.0.0", str(executable), digest, ("semantic.compile.java",), ("compiler.execute",), max_timeout_seconds=5.0)

    def test_unavailable_and_authority_mismatch_are_not_success(self) -> None:
        manifest = AdapterManifest("missing", "1", "/definitely/not/an/adapter", "0" * 64, ("x",), ())
        registry = AdapterRegistry((manifest,))
        result = registry.invoke(AdapterInvocation("missing", "x", {}))
        self.assertEqual(result.status, AdapterStatus.NOT_RUN)
        unsupported = registry.invoke(AdapterInvocation("unknown", "x", {}))
        self.assertEqual(unsupported.status, AdapterStatus.UNSUPPORTED)

    def test_exact_digest_capability_authority_and_request_binding(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._adapter(
                Path(temporary),
                """
                import json, sys
                request = json.load(sys.stdin)
                print(json.dumps({"request_digest": request["request_digest"], "nodes": []}))
                """,
            )
            registry = AdapterRegistry((manifest,), runtime_mode="local-engineering")
            invocation = AdapterInvocation("test-adapter", "semantic.compile.java", {"source_digest": "a" * 64}, ("compiler.execute",), 4.0, "request-1")
            denied = registry.invoke(invocation, caller_authority=())
            self.assertEqual(denied.status, AdapterStatus.DENIED)
            result = registry.invoke(invocation, caller_authority=("compiler.execute",))
            if result.status is AdapterStatus.NOT_RUN:
                self.assertIn("verified FD", result.reason)
                self.assertEqual(result.runtime_evidence, "NOT_RUN")
                return
            self.assertEqual(result.status, AdapterStatus.SUCCEEDED)
            self.assertEqual(result.output["request_digest"], invocation.request_digest)  # type: ignore[index]
            self.assertEqual(result.runtime_evidence, "LOCAL_EXECUTED_SELF_ATTESTED")
            self.assertEqual(result.sandbox_evidence, "NOT_RUN")
            self.assertEqual(result.network_isolation, "NOT_RUN")

    def test_cancel_is_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._adapter(
                Path(temporary),
                """
                import time
                time.sleep(5)
                """,
            )
            registry = AdapterRegistry((manifest,), runtime_mode="local-engineering")
            cancelled = threading.Event()
            cancelled.set()
            result = registry.invoke(AdapterInvocation("test-adapter", "semantic.compile.java", {}, ("compiler.execute",), 1.0), caller_authority=("compiler.execute",), cancel_event=cancelled)
            self.assertIn(
                result.status, {AdapterStatus.CANCELLED, AdapterStatus.NOT_RUN}
            )
            if result.status is AdapterStatus.NOT_RUN:
                self.assertIn("verified FD", result.reason)

    def test_production_denies_unsandboxed_execution_and_environment_injection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self._adapter(
                Path(temporary),
                """
                import json, sys
                request = json.load(sys.stdin)
                print(json.dumps({"request_digest": request["request_digest"]}))
                """,
            )
            invocation = AdapterInvocation(
                "test-adapter",
                "semantic.compile.java",
                {},
                ("compiler.execute",),
                4.0,
            )
            result = AdapterRegistry((manifest,)).invoke(
                invocation,
                caller_authority=("compiler.execute",),
            )
            self.assertEqual(result.status, AdapterStatus.NOT_RUN)
            self.assertIn("production", result.reason)
            self.assertEqual(result.runtime_evidence, "NOT_RUN")
        for environment in (
            {"LD_PRELOAD": "/tmp/inject"},
            {"DYLD_INSERT_LIBRARIES": "/tmp/inject"},
            {"PYTHONPATH": "/tmp/inject"},
            {"NODE_OPTIONS": "--require=/tmp/inject"},
            {"JAVA_TOOL_OPTIONS": "-agentlib:inject"},
            {"SERVICE_TOKEN": "secret"},
        ):
            with self.subTest(environment=environment):
                with self.assertRaises(ValueError):
                    AdapterManifest(
                        "unsafe",
                        "1",
                        "/bin/echo",
                        "0" * 64,
                        ("x",),
                        environment=environment,
                    )

    def test_executable_path_swap_never_runs_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "replacement-ran"
            manifest = self._adapter(
                root,
                """
                import time
                time.sleep(1)
                """,
            )
            executable = Path(manifest.executable)
            replacement = root / "replacement"
            replacement.write_text(
                f"#!{sys.executable}\nfrom pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('ran')\n",
                encoding="utf-8",
            )
            replacement.chmod(0o755)
            import subprocess

            real_popen = subprocess.Popen

            def swapping_popen(*args, **kwargs):
                replacement.replace(executable)
                return real_popen(*args, **kwargs)

            registry = AdapterRegistry(
                (manifest,), runtime_mode="local-engineering"
            )
            invocation = AdapterInvocation(
                "test-adapter",
                "semantic.compile.java",
                {},
                ("compiler.execute",),
                2.0,
            )
            with patch(
                "elmos_proof_harness.adapters.subprocess.Popen",
                side_effect=swapping_popen,
            ):
                result = registry.invoke(
                    invocation,
                    caller_authority=("compiler.execute",),
                )
            self.assertIn(result.status, {AdapterStatus.NOT_RUN, AdapterStatus.FAILED})
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
