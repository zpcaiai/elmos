from __future__ import annotations

import unittest

from elmos_formal_assurance.contracts import AssuranceLevel, ProofStatus
from elmos_formal_assurance.execution import (
    ADAPTERS,
    ExecutionContractError,
    ExecutionFile,
    ExecutionPermit,
    ExecutionState,
    NativeExecutionRequest,
    ProcessExecutionResult,
    interpret_tool_result,
)
from elmos_formal_assurance.lean_dafny_bridge import (
    DafnyGenerator,
    FormalProofBridgeError,
    Lean4Generator,
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _request(adapter_id: str, path: str, source: str) -> NativeExecutionRequest:
    permit = ExecutionPermit(
        permit_id="permit-source-boundary",
        nonce="nonce-source-boundary",
        tenant_id="tenant-a",
        account_id="account-a",
        project_id="project-a",
        skill_id="skill-source-boundary",
        subject_id="subject-source-boundary",
        adapter_id=adapter_id,
        execution_digest=_digest("1"),
        source_artifact_digest=_digest("2"),
        target_artifact_digest=_digest("3"),
        environment_digest=_digest("4"),
        issued_at_epoch=1,
        expires_at_epoch=2,
        signature="hmac-sha256:" + "5" * 64,
    )
    return NativeExecutionRequest(
        adapter_id=adapter_id,
        files=(ExecutionFile(path, source.encode("utf-8")),),
        options={},
        query_semantics="PROOF_CHECK",
        timeout_seconds=60,
        permit=permit,
        binding_digest=_digest("1"),
    )


class NativeSourceBoundaryTests(unittest.TestCase):
    def test_generators_reject_trust_escape_tokens(self) -> None:
        with self.assertRaises(FormalProofBridgeError):
            Lean4Generator.generate_theorem("unsafe_theorem", (), "True", ["sorry"])
        with self.assertRaises(FormalProofBridgeError):
            DafnyGenerator.generate_method(
                "unsafe_method",
                (),
                (),
                (),
                ("true",),
                "assume false;",
            )

    def test_native_lean_and_dafny_sources_require_real_obligations(self) -> None:
        with self.assertRaisesRegex(ExecutionContractError, "trust escape"):
            ADAPTERS["lean"].validate_request(
                _request("lean", "Main.lean", "theorem t : True := by sorry")
            )
        with self.assertRaisesRegex(ExecutionContractError, "no theorem"):
            ADAPTERS["lean"].validate_request(
                _request("lean", "Main.lean", "def helper := True")
            )
        with self.assertRaisesRegex(ExecutionContractError, "trust escape"):
            ADAPTERS["dafny"].validate_request(
                _request(
                    "dafny",
                    "input.dfy",
                    "method t() ensures true { assume false; }",
                )
            )
        with self.assertRaisesRegex(ExecutionContractError, "explicit proof obligation"):
            ADAPTERS["dafny"].validate_request(
                _request("dafny", "input.dfy", "method t() { }")
            )

    def test_dafny_zero_verified_is_not_promoted(self) -> None:
        request = _request(
            "dafny",
            "input.dfy",
            "method t() ensures true { }",
        )
        process = ProcessExecutionResult(
            state=ExecutionState.COMPLETED,
            exit_code=0,
            duration_ms=1,
            stdout=b"Dafny program verifier finished with 0 verified, 0 errors",
            stderr=b"",
            stdout_truncated=False,
            stderr_truncated=False,
            version_output="Dafny 4.4.0",
            containment="TEST",
            command_digest=_digest("6"),
        )
        status, assurance, diagnostics, counterexample = interpret_tool_result(
            ADAPTERS["dafny"], request, process
        )
        self.assertEqual(status, ProofStatus.UNSUPPORTED)
        self.assertEqual(assurance, AssuranceLevel.NONE)
        self.assertTrue(diagnostics)
        self.assertIsNone(counterexample)


if __name__ == "__main__":
    unittest.main()
