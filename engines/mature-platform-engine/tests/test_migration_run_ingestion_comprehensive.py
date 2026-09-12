"""Comprehensive test suite for MigrationRunIngestionEngine (B41 - Skill 1396)."""

import unittest

from elmos_mature_platform.migration_run_ingestion_engine import (
    MigrationRunIngestionEngine,
)
from elmos_mature_platform.types import (
    IngestedAssetType,
    IngestionQualityScore,
    MigrationRunSummary,
    RunIngestionArtifact,
)


class TestMigrationRunIngestionComprehensive(unittest.TestCase):
    def setUp(self):
        self.engine = MigrationRunIngestionEngine()

    def test_ingest_successful_migration_run(self):
        run = MigrationRunSummary(
            run_id="run-spring-01",
            project_name="LegacyBankingApp",
            source_tech="Java-Spring-Legacy",
            target_tech="SpringBoot3-CloudNative",
            success=True,
            files_migrated=145,
            transformations_applied=42,
            errors_encountered=["DeprecationWarning: javax.persistence to jakarta.persistence"],
        )
        artifacts = self.engine.ingest_migration_run(run)
        self.assertGreaterEqual(len(artifacts), 2)

        types = [a.asset_type for a in artifacts]
        self.assertIn(IngestedAssetType.PATTERN, types)
        self.assertIn(IngestedAssetType.ERROR_SOLUTION, types)
        self.assertIn(IngestedAssetType.FIXTURE, types)

    def test_ingest_failed_run_extracts_error_solutions(self):
        run = MigrationRunSummary(
            run_id="run-failed-cobol",
            project_name="CoreMainframePayroll",
            source_tech="COBOL",
            target_tech="Java",
            success=False,
            files_migrated=12,
            transformations_applied=5,
            errors_encountered=[
                "SyntaxError: COMP-3 packed decimal overflow at line 204",
                "ResolutionFailed: Missing copybook PAYROLL-REC",
            ],
        )
        artifacts = self.engine.ingest_migration_run(run)
        error_assets = [a for a in artifacts if a.asset_type == IngestedAssetType.ERROR_SOLUTION]
        self.assertEqual(len(error_assets), 2)

        # Fixture for failed run should have REJECTED quality
        fixture_asset = [a for a in artifacts if a.asset_type == IngestedAssetType.FIXTURE][0]
        self.assertEqual(fixture_asset.quality, IngestionQualityScore.REJECTED)

    def test_evaluate_artifact_quality(self):
        run = MigrationRunSummary(
            run_id="run-eval-q",
            project_name="TestApp",
            source_tech="PHP",
            target_tech="Go",
            success=True,
            transformations_applied=10,
        )
        artifacts = self.engine.ingest_migration_run(run)
        first_id = artifacts[0].artifact_id

        # Confidence is 0.92 -> VERIFIED
        score = self.engine.evaluate_artifact_quality(first_id)
        self.assertEqual(score, IngestionQualityScore.VERIFIED)

    def test_approve_artifact_for_curation(self):
        run = MigrationRunSummary(
            run_id="run-curate",
            project_name="Payments",
            source_tech="Python2",
            target_tech="Python3",
            success=True,
            transformations_applied=100,
        )
        artifacts = self.engine.ingest_migration_run(run)
        target = artifacts[0]

        approved = self.engine.approve_artifact_for_curation(target.artifact_id, "curator@company.org")
        self.assertEqual(approved.approved_by, "curator@company.org")
        self.assertEqual(approved.quality, IngestionQualityScore.VERIFIED)

    def test_approve_rejected_artifact_raises_error(self):
        run = MigrationRunSummary(
            run_id="run-bad",
            project_name="FailingProject",
            source_tech="C",
            target_tech="Rust",
            success=False,
        )
        artifacts = self.engine.ingest_migration_run(run)
        rejected_fixture = [a for a in artifacts if a.asset_type == IngestedAssetType.FIXTURE][0]

        with self.assertRaises(ValueError):
            self.engine.approve_artifact_for_curation(rejected_fixture.artifact_id, "curator")

    def test_query_harvested_assets(self):
        run1 = MigrationRunSummary("r1", "P1", "Java", "Kotlin", True, 50, 20)
        run2 = MigrationRunSummary("r2", "P2", "Java", "Kotlin", True, 30, 15)
        run3 = MigrationRunSummary("r3", "P3", "Python", "Go", True, 10, 5)

        self.engine.ingest_migration_run(run1)
        self.engine.ingest_migration_run(run2)
        self.engine.ingest_migration_run(run3)

        jk_patterns = self.engine.query_harvested_assets("Java", "Kotlin", IngestedAssetType.PATTERN)
        self.assertEqual(len(jk_patterns), 2)

        pygo_assets = self.engine.query_harvested_assets("Python", "Go")
        self.assertGreaterEqual(len(pygo_assets), 2)

    def test_get_flywheel_harvest_stats(self):
        run = MigrationRunSummary("r1", "Proj", "C#", "Go", True, 20, 10)
        artifacts = self.engine.ingest_migration_run(run)
        self.engine.approve_artifact_for_curation(artifacts[0].artifact_id, "lead-dev")

        stats = self.engine.get_flywheel_harvest_stats()
        self.assertEqual(stats["total_runs_ingested"], 1)
        self.assertEqual(stats["curated_approved_assets"], 1)
        self.assertIn("pattern", stats["assets_by_type"])


if __name__ == "__main__":
    unittest.main()
