#!/usr/bin/env python3
"""Negative integrity tests for the fail-closed FRT repository gate."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from external_evidence import validate_external_check
from run_frt_gate import (
    check_group,
    digest,
    evidence_digest,
    validate_evidence_ref,
    validate_result_binding,
)


class EvidenceReferenceTests(unittest.TestCase):
    def test_accepts_exact_content_addressed_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.json"
            evidence.write_bytes(b"immutable evidence\n")
            reference = {
                "path": "evidence.json",
                "sha256": "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest(),
                "bytes": evidence.stat().st_size,
            }
            self.assertEqual(validate_evidence_ref(reference, root), [])

    def test_rejects_missing_tampered_and_escaping_references(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence.json"
            evidence.write_bytes(b"immutable evidence\n")
            valid_digest = "sha256:" + hashlib.sha256(evidence.read_bytes()).hexdigest()
            self.assertTrue(validate_evidence_ref({
                "path": "missing.json", "sha256": valid_digest, "bytes": 19,
            }, root))
            self.assertTrue(validate_evidence_ref({
                "path": "evidence.json", "sha256": "sha256:" + "0" * 64, "bytes": 19,
            }, root))
            self.assertTrue(validate_evidence_ref({
                "path": "../outside.json", "sha256": valid_digest, "bytes": 19,
            }, root))
            self.assertTrue(validate_evidence_ref({
                "path": "evidence.json", "sha256": valid_digest, "bytes": 999,
            }, root))
            self.assertTrue(validate_evidence_ref({
                "path": "evidence.json", "sha256": valid_digest, "bytes": 19, "uri": "missing://x",
            }, root))

    def test_check_groups_reject_unknown_checks_and_fields(self) -> None:
        required = ("contract",)
        self.assertTrue(check_group("local_checks", {
            "contract": {"state": "NOT_RUN", "evidence_refs": []},
            "unexpected": {"state": "NOT_RUN", "evidence_refs": []},
        }, required))
        self.assertTrue(check_group("local_checks", {
            "contract": {"state": "NOT_RUN", "evidence_refs": [], "approved": True},
        }, required))

    def test_external_pass_cannot_be_claimed_without_independent_trust(self) -> None:
        self.assertEqual(
            validate_external_check(
                "performance",
                {"state": "PASSED", "evidence_refs": []},
                None,
            ),
            ["external_checks.performance PASSED requires an external trust store"],
        )

    def test_gate_result_is_bound_to_exact_request_bytes_and_its_own_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / "request.json"
            request.write_text('{"state":"current"}\n', encoding="utf-8")
            unsigned = {
                "schema_version": 1,
                "gate_request_sha256": evidence_digest(request),
                "decision": "READY_FOR_EXTERNAL_GATE",
            }
            result = {**unsigned, "result_digest": digest(unsigned)}
            self.assertEqual(validate_result_binding(result, request), [])
            request.write_text('{"state":"changed"}\n', encoding="utf-8")
            self.assertEqual(
                validate_result_binding(result, request),
                ["gate result is not bound to the current request bytes"],
            )
            result["decision"] = "CERTIFIED"
            self.assertIn("gate result digest mismatch", validate_result_binding(result, request))


if __name__ == "__main__":
    unittest.main()
