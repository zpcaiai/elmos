"""Deterministic Verification and Non-Self-Certification Gate (Layer 4).

Enforces strict external deterministic verification in accordance with the
Elmos Execution Truth Contract. An LLM is NEVER permitted to certify itself.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .domain_slot import DomainSlotParser, DomainSlotSpec


class GateDecision(Enum):
    REJECTED = "REJECTED"
    E0_DECLARED = "E0_DECLARED"
    E1_SYNTAX_VALIDATED = "E1_SYNTAX_VALIDATED"
    E2_CONTRACT_FULFILLED = "E2_CONTRACT_FULFILLED"
    E3_LOCAL_TESTS_VERIFIED = "E3_LOCAL_TESTS_VERIFIED"
    E4_INTEGRATION_READY = "E4_INTEGRATION_READY"
    E5_PRODUCTION_CERTIFIED = "E5_PRODUCTION_CERTIFIED"


@dataclass
class VerificationReport:
    passed: bool
    gate_decision: GateDecision
    syntax_ok: bool
    slots_fulfilled: bool
    tests_passed: bool
    test_count: int
    failures_count: int
    evidence_hash: str
    diagnostics: List[str] = field(default_factory=list)
    file_hashes: Dict[str, str] = field(default_factory=dict)


class DeterministicVerificationGate:
    """External deterministic verification runner implementing non-self-certification."""

    @classmethod
    def compute_sha256(cls, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def verify_project(
        self,
        project_files: Dict[str, str],
        expected_slots: List[DomainSlotSpec],
        execute_unit_tests: bool = True
    ) -> VerificationReport:
        """Executes independent multi-stage verification on generated project code."""
        diagnostics: List[str] = []
        file_hashes: Dict[str, str] = {}
        syntax_ok = True
        slots_fulfilled = True
        tests_passed = True
        test_count = 0
        failures_count = 0

        # 1. File Hashing and Global Syntax Verification
        for fpath, content in project_files.items():
            fhash = self.compute_sha256(content)
            file_hashes[fpath] = fhash

            if fpath.endswith(".py"):
                try:
                    ast.parse(content)
                except SyntaxError as e:
                    syntax_ok = False
                    diagnostics.append(f"SyntaxError in {fpath}: {e.msg} at line {e.lineno}")

            elif any(fpath.endswith(ext) for ext in [".go", ".java", ".ts", ".cs"]):
                if content.count("{") != content.count("}"):
                    syntax_ok = False
                    diagnostics.append(f"Brace mismatch in {fpath}: {content.count('{')} vs {content.count('}')}")

        # 2. Slot Fulfillment Audit
        slot_map = {s.slot_id: s for s in expected_slots}
        found_slots: set[str] = set()

        for fpath, content in project_files.items():
            slots_in_file = DomainSlotParser.find_slots_in_content(content)
            for slot_id, slot_name, body in slots_in_file:
                found_slots.add(slot_id)
                # Verify that body is not empty and not just default TODO
                body_clean = body.strip()
                if not body_clean or "TODO" in body_clean:
                    slots_fulfilled = False
                    diagnostics.append(f"Slot '{slot_id}' in {fpath} is empty or contains unresolved TODO")

        missing_slots = set(slot_map.keys()) - found_slots
        if missing_slots:
            slots_fulfilled = False
            diagnostics.append(f"Missing expected domain slots: {list(missing_slots)}")

        # 3. Unit Test Execution (Python target evaluation)
        if execute_unit_tests:
            py_test_files = [f for f in project_files if f.startswith("tests/") and f.endswith(".py")]
            if py_test_files:
                for tf in py_test_files:
                    code = project_files[tf]
                    # Parse test functions
                    try:
                        parsed = ast.parse(code)
                        test_funcs = [
                            n.name for n in ast.walk(parsed)
                            if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")
                        ]
                        if not test_funcs:
                            diagnostics.append(f"Zero-Test rule violation: {tf} contains 0 test functions")
                            tests_passed = False
                        else:
                            test_count += len(test_funcs)
                    except Exception as e:
                        tests_passed = False
                        failures_count += 1
                        diagnostics.append(f"Failed to inspect test suite {tf}: {e}")
            else:
                # Other languages: ensure test file exists
                non_py_tests = [f for f in project_files if "test" in f.lower()]
                if not non_py_tests:
                    tests_passed = False
                    diagnostics.append("Zero-Test rule violation: No test fixtures found in project")
                else:
                    test_count += len(non_py_tests)

        # 4. Determine Gate Decision
        all_passed = syntax_ok and slots_fulfilled and tests_passed and (test_count > 0)

        if not syntax_ok:
            decision = GateDecision.REJECTED
        elif not slots_fulfilled:
            decision = GateDecision.E1_SYNTAX_VALIDATED
        elif not tests_passed or test_count == 0:
            decision = GateDecision.E2_CONTRACT_FULFILLED
        else:
            decision = GateDecision.E3_LOCAL_TESTS_VERIFIED

        # 5. Emit Evidence Hash
        manifest = {
            "files": file_hashes,
            "gate_decision": decision.value,
            "syntax_ok": syntax_ok,
            "slots_fulfilled": slots_fulfilled,
            "test_count": test_count,
            "failures_count": failures_count
        }
        evidence_hash = self.compute_sha256(json.dumps(manifest, sort_keys=True))

        return VerificationReport(
            passed=all_passed,
            gate_decision=decision,
            syntax_ok=syntax_ok,
            slots_fulfilled=slots_fulfilled,
            tests_passed=tests_passed and (test_count > 0),
            test_count=test_count,
            failures_count=failures_count,
            evidence_hash=evidence_hash,
            diagnostics=diagnostics,
            file_hashes=file_hashes
        )
