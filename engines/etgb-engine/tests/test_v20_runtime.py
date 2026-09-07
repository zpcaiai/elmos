from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from elmos_etgb.discovery import load_surface, surface_coverage_report
from elmos_etgb.features import feature_coverage_report
from elmos_etgb.materializer import materialize, smoke_cases
from elmos_etgb.orchestrator import release_preflight
from elmos_etgb.package import verify_source_package
from elmos_etgb.planner import build_external_canary_plan, validate_plan_scope
from elmos_etgb.registry import SkillRegistry
from elmos_etgb.skills import audit_skills
from elmos_etgb.validation import runtime_adapter_report, validate_package

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "skills/elmos-etgb-full-product-assurance-skills-package-v2.0.0"
if not PACKAGE.is_dir():
    PACKAGE = ROOT / "skills/subskills/elmos-etgb-full-product-assurance-skills-package-v2.0.0"
ARCHIVE = ROOT / "skills/subskills/elmos-etgb-full-product-assurance-skills-package-v2.0.0.zip"
if not ARCHIVE.is_file():
    ARCHIVE = ROOT / "skills/subskills/elmos-etgb-full-product-assurance-skills-package-v2.0.0.tar.gz"


class V20FullProductRuntimeTests(unittest.TestCase):
    def test_package_v20_is_complete_and_source_is_digest_bound(self) -> None:
        source_result = verify_source_package(ARCHIVE, extracted=PACKAGE)
        self.assertTrue(source_result["valid"], source_result.get("errors"))
        self.assertTrue(source_result["archive_matches_pin"])
        self.assertEqual(len(source_result["skills"]), 50)

        result = validate_package(PACKAGE, archive=ARCHIVE, extracted=PACKAGE)
        self.assertTrue(result["valid"], result["errors"])
        self.assertEqual(result["case_count"], 75419)
        self.assertTrue(result["coverage"]["complete"])
        self.assertTrue(audit_skills(PACKAGE)["valid"])
        self.assertEqual(len(SkillRegistry(PACKAGE).describe()), 50)

    def test_feature_coverage_and_governance(self) -> None:
        report = feature_coverage_report(PACKAGE)
        self.assertTrue(report["complete"])
        self.assertEqual(report["feature_count"], 1452)
        self.assertEqual(report["domain_count"], 23)
        self.assertEqual(report["expected_case_bindings"], 23232)
        self.assertEqual(report["actual_case_bindings"], 23232)
        self.assertEqual(report["coverage_ratio"], 1.0)

        # Test through registry dispatch
        registry = SkillRegistry(PACKAGE)
        gov_report = registry.dispatch("full-product-coverage-governance", "feature_coverage")
        self.assertTrue(gov_report["complete"])

    def test_surface_coverage_and_audit(self) -> None:
        registry = SkillRegistry(PACKAGE)
        surface_path = PACKAGE / "integrations/discovered-surface.yaml"
        if not surface_path.is_file():
            surface_path = PACKAGE / "examples/product-surface.yaml"
        if surface_path.is_file():
            surface_data = load_surface(surface_path)
            audit = surface_coverage_report(PACKAGE, surface_data)
            self.assertTrue(audit["complete"])
            self.assertGreater(audit["implemented_surface_count"], 0)

            # Test through registry dispatch
            audit_dispatch = registry.dispatch(
                "full-product-coverage-governance",
                "surface_audit",
                {"surface": surface_data},
            )
            self.assertTrue(audit_dispatch["complete"])

    def test_all_50_skills_bound_in_registry(self) -> None:
        registry = SkillRegistry(PACKAGE)
        skills = registry.describe()
        self.assertEqual(len(skills), 50)
        skill_names = {s["name"] for s in skills}
        self.assertIn("full-product-coverage-governance", skill_names)
        self.assertIn("identity-access-tenant-validation", skill_names)
        self.assertIn("ai-solution-factory-validation", skill_names)
        self.assertIn("commercial-delivery-certification-validation", skill_names)
        self.assertIn("product-journey-validation", skill_names)
        self.assertIn("standards-assurance-validation", skill_names)

        # Test dispatching validate_case on domain validation skills
        dummy_case = {
            "id": "CASE-DUMMY-01",
            "business_line": "spring-modernization",
            "feature": "route-mapping",
            "inputs": {"sample": "data"},
            "expected": {"success": True},
        }
        res = registry.dispatch("identity-access-tenant-validation", "validate_case", {"case": dummy_case})
        self.assertIn("valid", res)

        # Test unavailable capability status fails closed
        cap = registry.dispatch("identity-access-tenant-validation", "capability")
        self.assertEqual(cap["status"], "EXTERNAL_ADAPTER_REQUIRED")
        self.assertFalse(cap["claimable"])
        self.assertEqual(cap["external_evidence"], "NOT_RUN")

    def test_materialize_and_smoke_cases(self) -> None:
        mat = materialize(PACKAGE)
        self.assertEqual(mat["total_cases"], 75419)
        smoke = smoke_cases(PACKAGE)
        self.assertEqual(len(smoke), 12)
        smoke_bls = {c["business_line"] for c in smoke}
        self.assertTrue({"spring-modernization", "cross-language", "project-generation", "sql-conversion"}.issubset(smoke_bls))

    def test_all_v20_adapters_are_bound_and_release_scope_is_exact(self) -> None:
        adapters = runtime_adapter_report(PACKAGE)
        self.assertTrue(adapters["complete"], adapters)
        self.assertEqual(len(adapters["declared_external_adapters"]), 32)
        self.assertEqual(len(adapters["declared_local_adapters"]), 4)
        self.assertEqual(adapters["unsupported_external_adapters"], [])

        preflight = release_preflight(PACKAGE, results=[])
        self.assertEqual(preflight["status"], "BLOCKED")
        self.assertEqual(preflight["scope"]["expected_cases"], 75419)
        self.assertEqual(preflight["scope"]["expected_case_runs"], 206671)
        self.assertEqual(preflight["scope"]["external_adapter_cases"], 75407)
        self.assertEqual(preflight["scope"]["external_adapter_case_runs"], 206659)

    def test_canary_plan_contains_one_stable_case_per_external_adapter(self) -> None:
        plan = build_external_canary_plan(
            PACKAGE,
            candidate_digest="sha256:" + "a" * 64,
            shard_count=4,
        )
        self.assertEqual(validate_plan_scope(PACKAGE, plan), [])
        self.assertEqual(len(plan["required_adapters"]), 32)
        self.assertEqual(len(plan["case_ids"]), 32)
        self.assertEqual(sum(shard["case_count"] for shard in plan["shards"]), 32)

    def test_git_ignored_source_evidence_is_present_and_digest_bound(self) -> None:
        expected = {
            "fixtures/cross-language/java-to-python-ledger/java/Ledger.class": "5c7981389bc3b7ccb3430721eb30dd9bb4f41f1ed12de475e3ac37dbf98fcd73",
            "reports/smoke-results.jsonl": "18bb510687a03906cd243d99fb7d43617fabb7fbbe65ec7aa142e87129e74902",
        }
        for relative, digest in expected.items():
            path = PACKAGE / relative
            self.assertTrue(path.is_file(), relative)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)
