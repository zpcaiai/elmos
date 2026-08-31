"""Unit and integration tests for Lean 4 & Dafny Formal Proof Bridge."""

from __future__ import annotations

import unittest

from elmos_formal_assurance.lean_dafny_bridge import (
    DafnyGenerator,
    FormalProofKernelBridge,
    Lean4Generator,
    generate_lean4_proof,
    get_formal_proof_bridge,
)


class Lean4DafnyBridgeTests(unittest.TestCase):
    """Test Lean 4 and Dafny proof specification synthesis."""

    def test_lean4_theorem_generation(self) -> None:
        thm = Lean4Generator.generate_theorem(
            theorem_name="NonNegativeBalance",
            hypotheses=["balance : Int", "h_pos : balance >= 0"],
            conclusion="balance >= 0",
            tactics=["intro h", "exact h"],
        )
        self.assertIn("theorem NonNegativeBalance", thm)
        self.assertIn("(h0 : balance : Int)", thm)
        self.assertIn("(h1 : h_pos : balance >= 0)", thm)
        self.assertIn("intro h", thm)
        self.assertIn("exact h", thm)

    def test_lean4_arithmetic_invariance(self) -> None:
        thm = Lean4Generator.generate_arithmetic_invariance_proof(
            theorem_name="PreserveIdentity",
            var_name="amt",
            var_type="Int",
            lower_bound=0,
            upper_bound=50000,
        )
        self.assertIn("theorem PreserveIdentity (amt : Int)", thm)
        self.assertIn("amt + 0 = amt", thm)
        self.assertIn("simp", thm)

    def test_dafny_method_generation(self) -> None:
        dfy = DafnyGenerator.generate_method(
            method_name="TransferFunds",
            params=[{"name": "fromBal", "type": "int"}, {"name": "amount", "type": "int"}],
            returns=[{"name": "newBal", "type": "int"}],
            requires=["fromBal >= amount", "amount > 0"],
            ensures=["newBal == fromBal - amount", "newBal >= 0"],
            body="newBal := fromBal - amount;",
        )
        self.assertIn("method TransferFunds(fromBal: int, amount: int) returns (newBal: int)", dfy)
        self.assertIn("requires fromBal >= amount", dfy)
        self.assertIn("ensures newBal == fromBal - amount", dfy)
        self.assertIn("newBal := fromBal - amount;", dfy)

    def test_dafny_loop_invariant(self) -> None:
        dfy = DafnyGenerator.generate_loop_invariance(
            method_name="SumArray",
            param_name="limit",
            invariant_cond="0 <= i <= limit",
        )
        self.assertIn("method SumArray(limit: int) returns (sum: int)", dfy)
        self.assertIn("invariant 0 <= i <= limit", dfy)
        self.assertIn("decreases limit - i", dfy)

    def test_formal_proof_certificate_synthesis(self) -> None:
        bridge = get_formal_proof_bridge()
        cert = bridge.synthesize_proof_certificate(
            obligation_name="MonetaryConservation",
            formula="sum(source_accounts) == sum(target_accounts)",
            source_lang="java",
            target_lang="rust",
        )
        self.assertIn("request_id", cert)
        self.assertTrue(cert["request_id"].startswith("proof-request-"))
        self.assertEqual(cert["verification_status"], "NATIVE_VERIFICATION_NOT_RUN")
        self.assertEqual(cert["soundness_guarantee"], "NOT_ASSESSED")
        self.assertEqual(cert["certification_status"], "NOT_CERTIFIED")
        self.assertIn("LEAN4_SOURCE_NOT_GENERATED", cert["gaps"])

    def test_cli_generate_lean4_proof_convenience(self) -> None:
        cert = generate_lean4_proof(
            obligation_name="SafeTypeCast",
            formula="cast(int64, x) == x",
            source_lang="csharp",
            target_lang="go",
        )
        self.assertEqual(cert["source_lang"], "csharp")
        self.assertEqual(cert["target_lang"], "go")
        self.assertEqual(cert["verification_status"], "NATIVE_VERIFICATION_NOT_RUN")
        self.assertFalse(cert["certificate_issued"])


if __name__ == "__main__":
    unittest.main()
