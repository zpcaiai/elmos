from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from elmos_pdhi.registry import resolve_operation
from elmos_pdhi.runtime_proof import K3_OPERATION_SPECS, RuntimeProofService
from elmos_pdhi.semantic import K1_OPERATION_SPECS, SemanticRuntime
from elmos_pdhi.transactions import K2_OPERATION_SPECS, ScopeFence, TransactionManager


K1 = {
    "semantic-lsp-federation", "compiler-authority-router", "repository-semantic-graph",
    "semantic-reference-index", "semantic-call-graph", "semantic-type-graph",
    "semantic-dataflow-index", "framework-semantic-detector", "ast-structural-query",
    "repository-prewalk-indexer", "cross-language-semantic-diff", "semantic-uncertainty-map",
}
K2 = {
    "semantic-anchor", "content-hash-anchor", "symbol-identity-anchor", "stale-state-detector",
    "read-set-tracker", "write-set-tracker", "patch-intent-contract", "edit-precondition-validator",
    "semantic-conflict-detector", "ast-structural-rewrite", "semantic-ir-rewrite",
    "framework-aware-rewrite", "edit-postcondition-validator", "transactional-patch",
    "snapshot-manager", "rollback-manager", "atomic-commit-planner",
    "dependency-aware-commit-ordering", "semantic-merge-validator", "merge-proof-generator",
}
K3 = {
    "dap-adapter-discovery", "dap-runtime-driver", "breakpoint-plan-generator",
    "runtime-state-capture", "call-stack-capture", "variable-snapshot", "exception-trace",
    "memory-state-probe", "differential-debugger", "control-flow-equivalence",
    "state-equivalence", "exception-equivalence", "api-response-equivalence",
    "database-effect-equivalence", "transaction-boundary-equivalence",
    "message-effect-equivalence", "file-effect-equivalence", "concurrency-observation",
    "deterministic-replay", "scenario-replay", "fault-injection-runner",
    "counterexample-generator", "runtime-root-cause-localizer", "auto-debug-repair-loop",
}


class BindingTests(unittest.TestCase):
    def test_all_catalog_operations_have_exact_concrete_bindings(self) -> None:
        self.assertEqual(K1, set(K1_OPERATION_SPECS))
        self.assertEqual(K2, set(K2_OPERATION_SPECS))
        self.assertEqual(K3, set(K3_OPERATION_SPECS))
        for owner, specs in (("K1", K1_OPERATION_SPECS), ("K2", K2_OPERATION_SPECS), ("K3", K3_OPERATION_SPECS)):
            for name, binding in specs.items():
                self.assertEqual(owner, resolve_operation(name).operation.canonical_owner)
                self.assertEqual(owner, binding.owner)
                self.assertEqual(name, binding.capability)
                runtime_type = SemanticRuntime if owner == "K1" else TransactionManager if owner == "K2" else RuntimeProofService
                self.assertTrue(hasattr(runtime_type, binding.method), name)

    def test_unknown_operation_has_no_fallback(self) -> None:
        with self.assertRaises(KeyError):
            SemanticRuntime().execute("unknown-operation")
        with self.assertRaises(KeyError):
            RuntimeProofService().execute("unknown-operation")
        with TemporaryDirectory() as repository:
            root = Path(repository)
            (root / "src").mkdir()
            manager = TransactionManager(ScopeFence(str(root), ("src",), "fence"))
            with self.assertRaises(KeyError):
                manager.execute("unknown-operation")


if __name__ == "__main__":
    unittest.main()
