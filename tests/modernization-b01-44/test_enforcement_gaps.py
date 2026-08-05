#!/usr/bin/env python3
"""Tests that close gaps found by ``mutation_check``.

Each test here exists because a mutation *survived* the rest of the suite:
some rule was enforced by the code but verified by nothing.  They target the
enforcement directly rather than through the happy path, because the happy path
is exactly what failed to notice.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.modernization_b01_44 import validation as validation_module  # noqa: E402
from scripts.modernization_b01_44.canonical import digest, format_instant  # noqa: E402
from scripts.modernization_b01_44.certification import (  # noqa: E402
    CertificationGate,
    required_evidence,
)
from scripts.modernization_b01_44.engine import DeterministicEngine  # noqa: E402
from scripts.modernization_b01_44.errors import (  # noqa: E402
    DeterminismViolation,
    SchemaViolation,
    UpstreamCertificateMissing,
)
from scripts.modernization_b01_44.evidence import EvidenceStore, make_evidence  # noqa: E402
from scripts.modernization_b01_44.packages import load_package, load_registry  # noqa: E402
from scripts.modernization_b01_44.policy import PolicyEngine  # noqa: E402

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)
REGISTRY = load_registry()


class UpstreamCertificateGapTest(unittest.TestCase):
    """M04: an empty upstream reference list must be refused at the gate."""

    def setUp(self):
        self.gate = CertificationGate(PolicyEngine(REGISTRY.get(9)), EvidenceStore())

    def test_empty_reference_list_is_refused(self):
        with self.assertRaises(UpstreamCertificateMissing) as ctx:
            self.gate.require_upstream(batch=9, certificate_refs=[], now=NOW)
        self.assertEqual(ctx.exception.code, "upstream-certificate-missing")

    def test_batch_one_needs_no_upstream(self):
        self.assertEqual(self.gate.require_upstream(batch=1, certificate_refs=[], now=NOW), [])


class PolicyDrivenEvidenceTest(unittest.TestCase):
    """M06: the certification policy file must actually change the gate."""

    def test_strict_policy_requires_holdout_and_representative(self):
        strict = required_evidence("certified", {})
        self.assertIn("holdout-corpus", strict)
        self.assertIn("representative-workload", strict)

    def test_relaxing_the_policy_relaxes_the_requirement(self):
        relaxed = required_evidence(
            "certified",
            {"holdout_required_for_certified": False, "representative_workload_required": False},
        )
        self.assertNotIn("holdout-corpus", relaxed)
        self.assertNotIn("representative-workload", relaxed)

    def test_shipped_policies_are_strict_for_every_batch(self):
        for package in REGISTRY:
            policy = PolicyEngine(package).certification_policy
            self.assertTrue(
                policy.get("holdout_required_for_certified"),
                f"batch {package.batch} does not require holdout evidence",
            )
            self.assertTrue(
                policy.get("representative_workload_required"),
                f"batch {package.batch} does not require a representative workload",
            )

    def test_gate_honours_a_relaxed_policy(self):
        """A package whose policy drops holdout grants certified without it."""

        store = EvidenceStore()
        gate = CertificationGate(PolicyEngine(REGISTRY.get(9)), store)
        gate.policy._certification = dict(  # noqa: SLF001 - deliberate policy swap
            gate.policy.certification_policy, holdout_required_for_certified=False
        )
        scopes = required_evidence("certified", gate.policy.certification_policy)
        for scope in scopes:
            store.add(
                make_evidence(
                    evidence_id=f"ev-{scope}",
                    producer="p",
                    created_at=NOW,
                    trust_level="runtime-observed",
                    scope=scope,
                    payload={"s": scope},
                    ttl=timedelta(days=10),
                )
            )
        decision = gate.evaluate(
            requested_status="certified", scope="s", evidence_refs=list(store.ids()), now=NOW
        )
        self.assertEqual(decision.granted_status, "certified")
        self.assertNotIn("holdout-corpus", scopes)


class WorkerInvarianceGapTest(unittest.TestCase):
    """M13: the *output* digest comparison must be the thing that fires."""

    def test_divergent_output_names_the_output_digest(self):
        engine = DeterministicEngine()
        counter = {"n": 0}

        def unstable(unit):
            counter["n"] += 1
            return {"i": unit["i"], "seq": counter["n"]}

        with self.assertRaises(DeterminismViolation) as ctx:
            engine.verify_worker_invariance(
                [{"i": i} for i in range(32)], unstable, worker_counts=(1, 4)
            )
        self.assertIn("output digest", ctx.exception.message)
        self.assertIn("observed_digest", ctx.exception.detail)


class ManifestVerificationGapTest(unittest.TestCase):
    """M19: a tampered package file must be reported, not loaded silently."""

    def _copy_package(self, batch: int, destination: Path) -> Path:
        source = REGISTRY.get(batch).path
        target = destination / source.name
        shutil.copytree(source, target)
        return target

    def test_clean_copy_loads_without_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self._copy_package(9, Path(tmp))
            self.assertEqual(load_package(target).problems, ())

    def test_tampered_byte_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self._copy_package(9, Path(tmp))
            victim = target / "policies" / "default-deny.yaml"
            victim.write_text(
                victim.read_text(encoding="utf-8").replace("network: true", "network: false"),
                encoding="utf-8",
            )
            problems = load_package(target).problems
            self.assertTrue(
                any(p.startswith("digest mismatch") for p in problems),
                f"tampering was not detected: {problems}",
            )

    def test_deleted_file_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = self._copy_package(9, Path(tmp))
            (target / "schemas" / "certification.schema.json").unlink()
            problems = load_package(target).problems
            self.assertTrue(any(p.startswith("manifest file missing") for p in problems))


class BuiltinValidatorGapTest(unittest.TestCase):
    """M20: the dependency-free validator path must be exercised too.

    ``jsonschema`` is normally present and shadows the built-in validator, so
    without these tests the fallback could rot unnoticed.
    """

    def setUp(self):
        self.schema = REGISTRY.get(9).schema("batch-input")
        self._had = validation_module._HAVE_JSONSCHEMA
        validation_module._HAVE_JSONSCHEMA = False

    def tearDown(self):
        validation_module._HAVE_JSONSCHEMA = self._had

    def _payload(self, **extra):
        payload = {
            "request_id": "r",
            "tenant_id": "t",
            "project_id": "p",
            "scope": "s",
            "upstream_certificate_refs": ["c"],
        }
        payload.update(extra)
        return payload

    def test_builtin_accepts_a_valid_payload(self):
        validation_module.validate(self._payload(), self.schema)

    def test_builtin_rejects_unknown_properties(self):
        with self.assertRaises(SchemaViolation) as ctx:
            validation_module.validate(self._payload(surprise=1), self.schema)
        self.assertIn("unknown_properties", ctx.exception.detail)

    def test_builtin_enforces_required(self):
        payload = self._payload()
        del payload["scope"]
        with self.assertRaises(SchemaViolation):
            validation_module.validate(payload, self.schema)

    def test_builtin_enforces_min_items(self):
        with self.assertRaises(SchemaViolation):
            validation_module.validate(
                self._payload(upstream_certificate_refs=[]), self.schema
            )

    def test_builtin_enforces_patterns(self):
        schema = REGISTRY.get(9).schema("evidence-ref")
        with self.assertRaises(SchemaViolation):
            validation_module.validate(
                {
                    "evidence_id": "e",
                    "digest": "nope",
                    "producer": "p",
                    "created_at": "2026-08-04T00:00:00Z",
                    "trust_level": "deterministic",
                    "scope": "s",
                },
                schema,
            )

    def test_builtin_enforces_const(self):
        schema = REGISTRY.get(9).schema("certification")
        with self.assertRaises(SchemaViolation):
            validation_module.validate(
                {
                    "certificate_id": "c",
                    "batch": 10,
                    "status": "limited",
                    "scope": "s",
                    "input_digests": ["a" * 64],
                    "evidence_refs": [],
                    "issued_at": "2026-08-04T00:00:00Z",
                    "expires_at": "2026-09-04T00:00:00Z",
                    "limitations": [],
                },
                schema,
            )

    def test_builtin_refuses_schemas_it_cannot_fully_enforce(self):
        with self.assertRaises(SchemaViolation):
            validation_module.validate({}, {"type": "object", "unevaluatedProperties": False})

    def test_both_validators_agree_on_every_shipped_schema(self):
        sample = self._payload()
        for package in REGISTRY:
            schema = package.schema("batch-input")
            validation_module._HAVE_JSONSCHEMA = False
            builtin_ok = validation_module.is_valid(sample, schema)
            validation_module._HAVE_JSONSCHEMA = self._had
            library_ok = validation_module.is_valid(sample, schema)
            self.assertEqual(
                builtin_ok, library_ok, f"validators disagree on batch {package.batch}"
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
