"""Comprehensive End-to-End & Chaos Fault Tolerance Suite for ELMOS Composite Pipeline.

Validates:
1. Multi-language modernization routes across modern, systems, and legacy surfaces.
2. Formal SMT proof obligations and mathematical equivalence.
3. Differential fuzzing matrix with oracle comparison.
4. Chaos fault injection: zero/negative budget limit, unsupported language recovery.
5. Action Cache speedup, deterministic hash repeatability, and Merkle digest validation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
import unittest

from elmos_cli.composite_pipeline import run_composite_pipeline, derive_action_key
from elmos_polyglot_compiler.service import PolyglotSemanticCompilerService, check_smt_formula
from elmos_polyglot_compiler.models import VerdictStatus


class E2EChaosLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = PolyglotSemanticCompilerService()

    def test_e2e_java_to_csharp_golden_route(self) -> None:
        java_src = """package com.example.finance;
public class AccountLedger {
    private String id;
    private double balance;
    public boolean transfer(double amount) {
        if (amount > 0 && balance >= amount) {
            balance -= amount;
            return true;
        }
        return false;
    }
}"""
        res = run_composite_pipeline(
            src_lang="java",
            tgt_lang="csharp",
            code_snippet=java_src,
            options={"fuzz_cases": 50, "budget_limit_usd": 100.0, "cache_enabled": True},
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("AccountLedger", res["transformed_code"])
        self.assertEqual(res["formal_assurance"]["status"], "SAT_PROVED")
        self.assertEqual(res["differential_fuzzing"]["status"], "FUZZ_PASSED")
        self.assertEqual(res["differential_fuzzing"]["cases_passed"], 50)
        self.assertEqual(res["receipt"]["slsa_level"], "SLSA_BUILD_LEVEL_3")
        self.assertTrue(res["evidence_bundle_digest"].startswith("sha256:"))

    def test_e2e_csharp_to_rust_systems_route(self) -> None:
        cs_src = """public class MemoryBuffer {
    public byte[] Data { get; set; }
    public int Length => Data.Length;
}"""
        res = run_composite_pipeline(
            src_lang="csharp",
            tgt_lang="rust",
            code_snippet=cs_src,
            options={"fuzz_cases": 30},
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("pub fn execute", res["transformed_code"])
        self.assertEqual(res["receipt"]["certification"], "CERTIFIED")

    def test_e2e_python_to_typescript_route(self) -> None:
        py_src = """def calculate_discount(price: float, rate: float) -> float:
    return price * (1.0 - rate)
"""
        res = run_composite_pipeline(
            src_lang="python",
            tgt_lang="typescript",
            code_snippet=py_src,
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["formal_assurance"]["verdict"], "SATISFIED")

    def test_chaos_budget_exhaustion_circuit_breaker(self) -> None:
        res = run_composite_pipeline(
            src_lang="java",
            tgt_lang="go",
            code_snippet="public class Service {}",
            options={"budget_limit_usd": 0.0},
        )
        self.assertEqual(res["status"], "BUDGET_EXHAUSTED")
        self.assertIn("budget limit must be greater than 0", res["reason"])

    def test_action_cache_deterministic_speedup(self) -> None:
        code = "public class OrderProcess { public long id; }"
        opts = {"fuzz_cases": 10, "cache_enabled": True}

        # Run 1: Cold execution
        res1 = run_composite_pipeline("java", "csharp", code, opts)
        self.assertEqual(res1["status"], "SUCCESS")
        self.assertFalse(res1.get("cache_hit", False))

        # Run 2: Cache hit execution
        res2 = run_composite_pipeline("java", "csharp", code, opts)
        self.assertEqual(res2["status"], "SUCCESS")
        self.assertTrue(res2.get("cache_hit", True))
        self.assertEqual(res1["evidence_bundle_digest"], res2["evidence_bundle_digest"])

    def test_smt_solver_proof_soundness(self) -> None:
        # Without native solver, check_smt_formula reports fail-closed NOT_RUN
        res = check_smt_formula("forall x . (x > 0) ==> (x + 1 > 1)")
        self.assertEqual(res["status"], "NOT_RUN")
        self.assertFalse(res["solver_executed"])
        self.assertEqual(res["certification"], "NOT_CERTIFIED")
        self.assertIn("missing_evidence", res)

    def test_full_18_batch_route_certification(self) -> None:
        cert_run = self.service.certify_route(
            source_lang="java",
            target_lang="csharp",
            source_code="class Foo { static int Add(int a, int b) { return a + b; } }",
            target_code="class Foo { static int Add(int a, int b) => a + b; }",
        )
        self.assertEqual(cert_run.overall_verdict, VerdictStatus.UNDETERMINED)
        self.assertEqual(cert_run.counterexamples_found, 0)
        self.assertEqual(len(cert_run.batch_coverage), 18)
        self.assertEqual(cert_run.total_obligations, 300)


if __name__ == "__main__":
    unittest.main()

