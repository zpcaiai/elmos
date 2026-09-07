#!/usr/bin/env python3
"""Positive and adversarial tests for signed FRT external evidence."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from external_campaign_parameters import test_parameters
from external_evidence import (
    PROFILE,
    digest_file,
    record_payload,
    signature_envelope,
    validate_external_check,
    validate_external_record,
    write_json,
)


class ExternalEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run = self.root / "run-001"
        self.run.mkdir()
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.started = self.now - timedelta(minutes=10)
        self.completed = self.now - timedelta(minutes=5)
        self.profile = self.root / "external-evidence-profile.json"
        self.profile.write_bytes(PROFILE.read_bytes())
        self.keys: dict[str, tuple[Path, Path]] = {}
        principals = {
            "EXECUTOR": ("executor-1", "executor-org"),
            "VERIFIER": ("verifier-1", "verifier-org"),
            "APPROVER": ("approver-1", "owner-org"),
        }
        trust_keys: list[dict[str, Any]] = []
        for role, (principal, organization) in principals.items():
            private = self.root / f"{role.lower()}-private.pem"
            public = self.root / f"{role.lower()}-public.pem"
            subprocess.run(
                ["openssl", "genpkey", "-algorithm", "ed25519", "-out", str(private)],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["openssl", "pkey", "-in", str(private), "-pubout", "-out", str(public)],
                check=True,
                capture_output=True,
            )
            self.keys[role] = (private, public)
            trust_keys.append(
                {
                    "key_id": f"{role.lower()}-key",
                    "principal_id": principal,
                    "organization_id": organization,
                    "roles": [role],
                    "public_key_path": public.name,
                    "valid_from": (self.now - timedelta(days=1)).isoformat(),
                    "expires_at": (self.now + timedelta(days=1)).isoformat(),
                    "revoked": False,
                }
            )
        self.trust = self.root / "trust-store.json"
        write_json(
            self.trust,
            {"schema_version": 1, "store_id": "test-store", "keys": trust_keys},
        )
        self.scope = {
            "profile_sha256": digest_file(self.profile),
            "package_manifest_sha256": "sha256:" + "1" * 64,
            "source_tree_sha256": "sha256:" + "2" * 64,
        }
        self.authorization_path = self.run / "authorization.json"
        self.record_path = self.run / "record.json"
        self.profile_value = json.loads(self.profile.read_text(encoding="utf-8"))
        self._configure_check("performance")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _authorization(self) -> dict[str, Any]:
        value = {
            "schema_version": 1,
            "authorization_id": "auth-001",
            "pack_key": "frt-g01-g30-platform",
            "check_id": self.check_id,
            "purpose": f"independent {self.check_id} qualification",
            "environment": f"runner-{self.check_id.replace('_', '-')}-1",
            "evidence_root": "run-001",
            "runner_capability": self.spec["runner_capability"],
            "run_parameters": test_parameters(self.check_id),
            "valid_from": (self.started - timedelta(minutes=5)).isoformat(),
            "expires_at": (self.completed + timedelta(minutes=5)).isoformat(),
            "approver": {
                "principal_id": "approver-1",
                "organization_id": "owner-org",
            },
            "signature": None,
        }
        from external_evidence import authorization_payload

        value["signature"] = signature_envelope(
            authorization_payload(value),
            self.keys["APPROVER"][0],
            "approver-key",
            "APPROVER",
            self.started.isoformat(),
        )
        return value

    def _evidence(self, role: str) -> dict[str, Any]:
        path = self.authorization_path if role == "authorization" else self.run / f"{role}.json"
        if role != "authorization":
            path.write_text(json.dumps({"role": role, "result": "PASSED"}) + "\n")
        return {
            "role": role,
            "path": path.relative_to(self.root).as_posix(),
            "sha256": digest_file(path),
            "bytes": path.stat().st_size,
            "media_type": "application/json",
            "classification": "INTERNAL",
            "redacted": False,
            "contains_personal_data": False,
        }

    def _record(self) -> dict[str, Any]:
        roles = self.spec["required_evidence_roles"]
        return {
            "schema_version": 1,
            "record_type": "FRT_EXTERNAL_EVIDENCE",
            "pack_key": "frt-g01-g30-platform",
            "check_id": self.check_id,
            "run_id": "run-001",
            "authorization_ref": {
                "path": self.authorization_path.relative_to(self.root).as_posix(),
                "sha256": digest_file(self.authorization_path),
                "bytes": self.authorization_path.stat().st_size,
            },
            **self.scope,
            "status": "PASSED",
            "started_at": self.started.isoformat(),
            "completed_at": self.completed.isoformat(),
            "executor": {
                "principal_id": "executor-1",
                "organization_id": "executor-org",
            },
            "verifier": {
                "principal_id": "verifier-1",
                "organization_id": "verifier-org",
            },
            "approver": {
                "principal_id": "approver-1",
                "organization_id": "owner-org",
            },
            "environment": {
                "runner_id": f"runner-{self.check_id.replace('_', '-')}-1",
                "runner_version": "1.0.0",
                "os": "linux-6.12",
                "architecture": "x86_64",
                "tool_versions": {"external-evidence-protocol": "1.0.0", "openssl": "3"},
                "region": "isolated-test-region",
                "network_policy": "approved-targets-only",
            },
            "metrics": self._valid_metrics(),
            "findings": {"critical": 0, "high": 0, "medium": 0, "low": 0, "unresolved": 0},
            "claims": {claim: True for claim in self.spec["required_claims"]},
            "evidence": [self._evidence(role) for role in roles],
            "signatures": [],
        }

    def _valid_metrics(self) -> dict[str, int | float]:
        metrics: dict[str, int | float] = {
            metric: 1 for metric in self.spec["required_metrics"]
        }
        for metric, value in self.spec.get("exact_metrics", {}).items():
            metrics[metric] = value
        for metric, value in self.spec.get("minimum_metrics", {}).items():
            metrics[metric] = max(metrics[metric], value)
        for left, right in self.spec.get("equal_metric_pairs", []):
            shared = max(metrics[left], metrics[right])
            metrics[left] = shared
            metrics[right] = shared
        for actual, budget in self.spec.get("less_or_equal_metric_pairs", []):
            metrics[budget] = max(metrics[budget], metrics[actual])
            metrics[actual] = min(metrics[actual], metrics[budget])
        return metrics

    def _configure_check(self, check_id: str) -> None:
        self.check_id = check_id
        self.spec = self.profile_value["checks"][check_id]
        self.authorization = self._authorization()
        write_json(self.authorization_path, self.authorization)
        self.record = self._record()
        self._sign_record()

    def _sign_record(self) -> None:
        self.record["signatures"] = [
            signature_envelope(
                record_payload(self.record),
                self.keys[role][0],
                f"{role.lower()}-key",
                role,
                self.completed.isoformat(),
            )
            for role in ("EXECUTOR", "VERIFIER", "APPROVER")
        ]
        write_json(self.record_path, self.record)

    def validate(self) -> list[str]:
        return validate_external_record(
            self.record_path,
            self.trust,
            evidence_root=self.root,
            profile_path=self.profile,
            enforce_pack_paths=False,
            now=self.now,
            expected_scope=self.scope,
        )

    def test_accepts_exact_independent_signed_record_for_every_external_check(self) -> None:
        for check_id in self.profile_value["checks"]:
            with self.subTest(check_id=check_id):
                self._configure_check(check_id)
                self.assertEqual(self.validate(), [])

    def test_every_external_check_rejects_a_profile_metric_violation(self) -> None:
        for check_id in self.profile_value["checks"]:
            with self.subTest(check_id=check_id):
                self._configure_check(check_id)
                exact = self.spec.get("exact_metrics", {})
                equal = self.spec.get("equal_metric_pairs", [])
                minimum = self.spec.get("minimum_metrics", {})
                if exact:
                    metric, expected = next(iter(exact.items()))
                    self.record["metrics"][metric] = expected + 1
                elif equal:
                    left, right = equal[0]
                    self.record["metrics"][right] = self.record["metrics"][left] + 1
                else:
                    metric, threshold = next(iter(minimum.items()))
                    self.record["metrics"][metric] = threshold - 1
                self._sign_record()
                self.assertTrue(any(item.startswith("metric") or item.startswith("metrics") for item in self.validate()))

    def test_rejects_self_verification_even_with_valid_evidence(self) -> None:
        self.record["verifier"]["organization_id"] = "executor-org"
        self._sign_record()
        self.assertIn("executor and verifier organizations must differ", self.validate())

    def test_rejects_verifier_as_approver(self) -> None:
        self.record["approver"]["principal_id"] = "verifier-1"
        self._sign_record()
        self.assertIn("verifier and approver principals must differ", self.validate())

    def test_rejects_weakened_metric_and_missing_role(self) -> None:
        self.record["metrics"]["workloads_passed"] = self.record["metrics"]["workloads_expected"] - 1
        self.record["evidence"] = self.record["evidence"][:-1]
        self._sign_record()
        failures = self.validate()
        self.assertIn("metrics workloads_expected and workloads_passed must be equal", failures)
        self.assertTrue(any("record evidence roles must be exact" in item for item in failures))

    def test_rejects_tampered_raw_evidence(self) -> None:
        raw = self.run / "raw_performance_results.json"
        raw.write_text('{"tampered":true}\n')
        self.assertTrue(any("sha256 mismatch" in item for item in self.validate()))

    def test_gate_rejects_passed_external_check_without_trust_store(self) -> None:
        failures = validate_external_check(
            "performance",
            {"state": "PASSED", "evidence_refs": []},
            None,
            self.root,
        )
        self.assertEqual(
            failures,
            ["external_checks.performance PASSED requires an external trust store"],
        )


if __name__ == "__main__":
    unittest.main()
