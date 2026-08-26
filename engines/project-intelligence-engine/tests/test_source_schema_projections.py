from __future__ import annotations

import hashlib
import unittest

from elmos_project_intelligence.domain import TrustedRuntimeScope
from elmos_project_intelligence.source_schema_projections import (
    SchemaProjectionError,
    build_analysis_job_plan,
    build_evidence_bundle,
    build_graph_snapshot,
    build_project_manifest,
    build_skill_output,
    validate_conversion_mapping,
    validate_trace_link,
)


class SourceSchemaProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scope = TrustedRuntimeScope(
            tenant_id="tenant-a", project_id="project-a", revision="rev-a"
        )
        self.digest = hashlib.sha256(b"print('ok')").hexdigest()

    def test_project_graph_and_evidence_projections_bind_scope(self) -> None:
        manifest = build_project_manifest(
            self.scope,
            [{"path": "src/app.py", "text": "print('ok')"}],
            observed_at="2026-08-26T00:00:00Z",
        )
        self.assertEqual(manifest["tenant_id"], "tenant-a")
        self.assertEqual(manifest["revision_id"], "rev-a")
        self.assertEqual(manifest["files"][0]["sha256"], self.digest)

        graph = build_graph_snapshot(
            self.scope,
            nodes=[
                {"stable_key": "api", "kind": "service", "evidence_refs": ["ev-1"]},
                {"id": "store", "kind": "database"},
            ],
            edges=[{"source": "api", "target": "store", "kind": "writes"}],
            evidence_ids=["ev-1"],
        )
        self.assertEqual(graph["project_id"], "project-a")
        self.assertEqual(graph["edges"][0]["source"], graph["nodes"][0]["id"])
        self.assertEqual(graph["quality"]["verification_state"], "NOT_RUN")

        bundle = build_evidence_bundle(
            self.scope,
            claims=[
                {
                    "claim_id": "claim-1",
                    "text": "The source contains an application entry point.",
                    "evidence_refs": ["ev-1"],
                }
            ],
            evidence=[
                {
                    "evidence_id": "ev-1",
                    "kind": "source",
                    "path": "src/app.py",
                    "hash": self.digest,
                }
            ],
        )
        self.assertEqual(bundle["tenant_id"], "tenant-a")
        self.assertEqual(bundle["claims"][0]["status"], "inferred")

    def test_plans_and_cross_skill_contracts_remain_non_authoritative(self) -> None:
        plan = build_analysis_job_plan(
            self.scope,
            [{"name": "parse", "total_units": 2}, "graph"],
            job_type="project-analysis",
            workflow_version="v1",
        )
        self.assertEqual(plan["state"], "queued")
        self.assertTrue(all(stage["attempt"] == 0 for stage in plan["stages"]))
        self.assertNotIn("created_at", plan)

        mapping = validate_conversion_mapping(
            {
                "mapping_id": "mapping-1",
                "source_revision_id": "source-a",
                "target_revision_id": "target-a",
                "entries": [
                    {
                        "entry_id": "entry-1",
                        "source_ref": "src/app.py:1",
                        "target_ref": "target/app.py:1",
                        "status": "partial",
                        "confidence": 0.5,
                    }
                ],
            }
        )
        self.assertEqual(mapping["entries"][0]["status"], "partial")

        trace = validate_trace_link(
            {
                "link_id": "link-1",
                "project_id": "project-a",
                "revision_id": "rev-a",
                "environment": "local",
                "time_window": {
                    "from": "2026-08-26T00:00:00Z",
                    "to": "2026-08-26T00:01:00Z",
                },
                "span_ref": "span-1",
                "target_refs": ["src/app.py:1"],
                "confidence": 0.25,
            }
        )
        self.assertEqual(trace["project_id"], "project-a")

        output = build_skill_output(
            skill="elmos-project-fingerprinting",
            revision="rev-a",
            known_limitations=["native toolchain execution remains NOT_RUN"],
            test_commands=["make project-intelligence-skills"],
            changed_files=["src/app.py"],
        )
        self.assertEqual(output["status"], "partial")
        self.assertEqual(output["tests"][0]["result"], "not_run")
        self.assertEqual(output["evidence"], [])

    def test_projection_rejects_scope_or_evidence_promotion(self) -> None:
        with self.assertRaises(SchemaProjectionError):
            build_graph_snapshot(
                self.scope,
                nodes=[{"id": "api", "kind": "service"}],
                edges=[{"source": "api", "target": "missing", "kind": "calls"}],
            )
        with self.assertRaises(SchemaProjectionError):
            build_evidence_bundle(
                self.scope,
                claims=[
                    {
                        "claim_id": "claim-1",
                        "text": "forged",
                        "status": "confirmed",
                        "confidence": 1,
                        "evidence_refs": [],
                        "verified": True,
                    }
                ],
                evidence=[],
            )


if __name__ == "__main__":
    unittest.main()
