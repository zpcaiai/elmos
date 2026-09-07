#!/usr/bin/env python3
"""Package integrity and the full Batch 01 -> Batch 44 chain.

The package tests assert that what is on disk is what the manifests claim.  The
chain tests assert that certification actually flows: Batch N cannot run unless
Batch N-1 issued something real, and breaking any link stops the chain there.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.modernization_b01_44.canonical import digest_bytes, format_instant  # noqa: E402
from scripts.modernization_b01_44.certification import Certificate  # noqa: E402
from scripts.modernization_b01_44.errors import (  # noqa: E402
    CertificationBlocked,
    UpstreamCertificateMissing,
)
from scripts.modernization_b01_44.generate_foundation import main as generate_main  # noqa: E402
from scripts.modernization_b01_44.orchestrator import (  # noqa: E402
    ChainRunner,
    Platform,
    standard_corpus,
)
from scripts.modernization_b01_44.packages import (  # noqa: E402
    REQUIRED_POLICIES,
    REQUIRED_SCHEMAS,
    SKILL_ARCHETYPES,
    load_registry,
)
from scripts.modernization_b01_44.policy import Principal  # noqa: E402
from scripts.modernization_b01_44.validation import validate  # noqa: E402

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)
REGISTRY = load_registry()
EXPECTED_BATCHES = 44


class PackageIntegrityTest(unittest.TestCase):
    def test_all_forty_four_batches_load(self):
        self.assertEqual(len(REGISTRY), EXPECTED_BATCHES)
        self.assertEqual(sorted(REGISTRY.packages), list(range(1, EXPECTED_BATCHES + 1)))

    def test_no_package_reports_problems(self):
        incomplete = REGISTRY.incomplete_batches()
        self.assertEqual(incomplete, {}, f"incomplete packages: {incomplete}")

    def test_every_manifest_digest_matches_disk(self):
        for package in REGISTRY:
            declared = len(package.manifest.get("files", []))
            self.assertGreater(declared, 0, f"batch {package.batch} declares no files")
            self.assertEqual(
                package.verified_files,
                declared,
                f"batch {package.batch}: {declared - package.verified_files} files failed verification",
            )

    def test_every_batch_provides_all_sixteen_archetypes(self):
        for package in REGISTRY:
            for archetype in SKILL_ARCHETYPES:
                skill = package.skill(archetype)
                self.assertTrue(skill.name, f"batch {package.batch}/{archetype} has no name")

    def test_every_batch_provides_the_runtime_schemas_and_policies(self):
        for package in REGISTRY:
            for name in REQUIRED_SCHEMAS:
                self.assertIn("$id", package.schema(name))
            for name in REQUIRED_POLICIES:
                self.assertTrue(package.policy(name))

    def test_certification_schema_pins_its_own_batch(self):
        for package in REGISTRY:
            self.assertEqual(
                package.schema("certification")["properties"]["batch"]["const"],
                package.batch,
                f"batch {package.batch} certification schema is not self-pinned",
            )

    def test_every_batch_declares_twelve_obligations(self):
        for package in REGISTRY:
            self.assertEqual(
                len(package.test_cases), 12, f"batch {package.batch} test catalog is not 12 cases"
            )

    def test_skill_names_are_globally_unique(self):
        seen: dict[str, int] = {}
        for package in REGISTRY:
            for skill in package.skills.values():
                if skill.name in seen and seen[skill.name] != package.batch:
                    self.fail(f"{skill.name} appears in batches {seen[skill.name]} and {package.batch}")
                seen[skill.name] = package.batch

    def test_package_native_validators_pass(self):
        for package in REGISTRY:
            validator = package.path / "tools" / "validate_package.py"
            if not validator.is_file():
                continue
            proc = subprocess.run(
                [sys.executable, "tools/validate_package.py"],
                cwd=package.path,
                capture_output=True,
                text=True,
                env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin"},
            )
            self.assertEqual(
                proc.returncode, 0, f"batch {package.batch} validator failed:\n{proc.stdout}{proc.stderr}"
            )

    def test_generated_foundation_content_is_committed(self):
        """`--check` must report no drift: the tree matches the generator."""

        self.assertEqual(generate_main(["--check"]), 0)

    def test_foundation_examples_validate_against_their_schemas(self):
        for batch in (1, 2, 3, 4, 5):
            package = REGISTRY.get(batch)
            for example in sorted((package.path / "examples").rglob("*.yaml")):
                text = example.read_text(encoding="utf-8")
                self.assertIn("record_id", text, f"{example} is not a schema instance")


class ChainTest(unittest.TestCase):
    def setUp(self):
        self.platform = Platform(registry=REGISTRY)
        self.principal = Principal("u-1", "tenant-a", "human")
        self.corpus = standard_corpus("svc-chain", assets=["a", "b", "c"])

    def _run(self, batches, **kwargs):
        return ChainRunner(self.platform).run(
            batches,
            principal=self.principal,
            tenant_id="tenant-a",
            project_id="proj",
            scope="svc-chain",
            now=NOW,
            corpus=self.corpus,
            options={"assets": ["a", "b", "c"]},
            **kwargs,
        )

    def test_full_chain_executes_end_to_end(self):
        results = self._run(range(1, EXPECTED_BATCHES + 1))
        self.assertEqual(len(results), EXPECTED_BATCHES)
        for result in results:
            self.assertIn(result.status, ("completed", "partial"))
            self.assertIsNotNone(result.certificate)
            self.assertEqual(result.certificate.status, "limited")
        self.assertEqual(len(self.platform.certificates), EXPECTED_BATCHES)
        self.assertEqual(len(self.platform.workflows), EXPECTED_BATCHES)

    def test_each_batch_consumes_its_predecessors_certificate(self):
        results = self._run(range(1, 6))
        for downstream, upstream in zip(results[1:], results[:-1]):
            self.assertIsNotNone(upstream.certificate)
            self.assertEqual(upstream.certificate.batch, downstream.batch - 1)

    def test_breaking_a_link_stops_the_chain(self):
        results = self._run(range(1, 4))
        broken = results[-1].certificate.certificate_id
        self.platform.gate(3).revoke(broken, "test-injected")
        with self.assertRaises(CertificationBlocked):
            ChainRunner(self.platform).run(
                [4],
                principal=self.principal,
                tenant_id="tenant-a",
                project_id="proj",
                scope="svc-chain",
                now=NOW,
                corpus=self.corpus,
                seed_upstream_refs=[broken],
                options={"assets": ["a", "b", "c"]},
            )

    def test_chain_is_deterministic_across_platforms(self):
        first = self._run(range(1, 6))
        second = ChainRunner(Platform(registry=REGISTRY)).run(
            range(1, 6),
            principal=self.principal,
            tenant_id="tenant-a",
            project_id="proj",
            scope="svc-chain",
            now=NOW,
            corpus=self.corpus,
            options={"assets": ["a", "b", "c"]},
        )
        self.assertEqual(
            [r.output_digest for r in first], [r.output_digest for r in second]
        )
        self.assertEqual(
            [r.certificate.certificate_id for r in first],
            [r.certificate.certificate_id for r in second],
        )

    def test_evidence_accumulates_and_is_linked(self):
        self._run(range(1, 6))
        self.assertGreater(len(self.platform.evidence), 20)
        linked = [node for node, ups in self.platform.lineage.edges.items() if ups]
        self.assertTrue(linked, "no lineage edges were recorded")

    def test_outputs_validate_against_each_batch_schema(self):
        for result in self._run(range(1, 6)):
            package = REGISTRY.get(result.batch)
            validate(result.as_output(), package.schema("batch-output"))
            validate(result.certificate.as_dict(), package.schema("certification"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
