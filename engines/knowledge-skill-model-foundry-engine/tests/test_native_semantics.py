"""Exact native semantic program inventory and execution-trace boundaries."""

from __future__ import annotations

from copy import deepcopy
import unittest

from elmos_foundry.canonical import canonical_digest
from elmos_foundry.local_semantics import LOCAL_SEMANTIC_SKILLS
from elmos_foundry.native_semantics import (
    NATIVE_TRACE_SCHEMA_VERSION,
    NativeSemanticError,
    NativeSemanticProgram,
    load_native_programs,
    native_program_for,
)
from elmos_foundry.skills import load_compiled_catalog


def valid_trace(program: NativeSemanticProgram, request_digest: str) -> dict[str, object]:
    """Build a deterministic provider trace for contract validation tests."""

    stages: list[dict[str, object]] = []
    input_digest = request_digest
    for expected in program.stages:
        index = int(expected["index"])
        output_digest = canonical_digest(
            {"program": program.digest, "stage": index, "input": input_digest}
        )
        stages.append(
            {
                "index": index,
                "name": expected["name"],
                "operation": expected["operation"],
                "status": "SUCCEEDED",
                "input_digest": input_digest,
                "output_digest": output_digest,
                "checkpoint_digest": canonical_digest(
                    {"program": program.digest, "checkpoint": index}
                ),
                "tool_receipts": [
                    {
                        "tool": tool,
                        "outcome": "CONFIRMED",
                        "receipt_digest": canonical_digest(
                            {"program": program.digest, "stage": index, "tool": tool}
                        ),
                    }
                    for tool in expected["tools"]
                ],
            }
        )
        input_digest = output_digest
    execution = {
        "schema_version": NATIVE_TRACE_SCHEMA_VERSION,
        "skill_name": program.skill_name,
        "handler_id": program.handler_id,
        "program_digest": program.digest,
        "request_binding_digest": request_digest,
        "stages": stages,
        "gate_evidence": [
            {
                "gate": gate,
                "status": "PASSED",
                "evidence_digest": canonical_digest(
                    {"program": program.digest, "gate": gate}
                ),
            }
            for gate in program.required_gates
        ],
        "rollback": {
            "strategy": program.rollback_strategy,
            "status": "NOT_REQUIRED",
            "receipt_digest": canonical_digest(
                {"program": program.digest, "rollback": "NOT_REQUIRED"}
            ),
        },
    }
    return {"semantic_execution": execution}


class NativeSemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_compiled_catalog()
        cls.programs = load_native_programs()

    def test_every_non_local_skill_has_one_exact_unique_program(self) -> None:
        expected = set(self.catalog.atomic_skills) - set(LOCAL_SEMANTIC_SKILLS)
        self.assertEqual(expected, set(self.programs))
        self.assertEqual(1_244, len(self.programs))
        self.assertEqual(1_244, len({program.handler_id for program in self.programs.values()}))
        self.assertEqual(1_244, len({program.digest for program in self.programs.values()}))
        for name in sorted(expected):
            program = native_program_for(name, self.catalog.atomic_skills[name])
            self.assertEqual(f"native.{name}", program.handler_id)
            self.assertEqual(7, len(program.stages))

    def test_exact_trace_is_accepted(self) -> None:
        program = self.programs["a2a-agent-discovery-messaging"]
        request_digest = canonical_digest({"request": "exact"})
        program.validate_result(valid_trace(program, request_digest), request_binding_digest=request_digest)

    def test_foreign_reordered_or_unverified_trace_fails_closed(self) -> None:
        program = self.programs["a2a-agent-discovery-messaging"]
        request_digest = canonical_digest({"request": "exact"})
        baseline = valid_trace(program, request_digest)
        mutations = []
        wrong_program = deepcopy(baseline)
        wrong_program["semantic_execution"]["program_digest"] = "0" * 64  # type: ignore[index]
        mutations.append(wrong_program)
        reordered = deepcopy(baseline)
        reordered["semantic_execution"]["stages"].reverse()  # type: ignore[index,union-attr]
        mutations.append(reordered)
        failed_gate = deepcopy(baseline)
        failed_gate["semantic_execution"]["gate_evidence"][0]["status"] = "FAILED"  # type: ignore[index]
        mutations.append(failed_gate)
        unverified_tool = deepcopy(baseline)
        stages = unverified_tool["semantic_execution"]["stages"]  # type: ignore[index]
        receipt = next(stage["tool_receipts"][0] for stage in stages if stage["tool_receipts"])  # type: ignore[index,union-attr]
        receipt["outcome"] = "UNKNOWN"
        mutations.append(unverified_tool)
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                with self.assertRaises(NativeSemanticError):
                    program.validate_result(mutation, request_binding_digest=request_digest)


if __name__ == "__main__":
    unittest.main()
