import unittest
from pathlib import Path
from elmos_project_intelligence.task_execution.subsystem_pipelines import (
    SubsystemPipelineOrchestrator,
    PipelineExecutionBundle,
)


class TestSubsystemPipelines(unittest.TestCase):
    def setUp(self):
        self.orchestrator = SubsystemPipelineOrchestrator()

    def test_run_full_analysis_pipeline(self):
        bundle = self.orchestrator.run_full_analysis_pipeline(
            project_path=Path(__file__).resolve().parent,
            tenant_id="test-tenant",
            project_id="test-project",
        )
        self.assertIsInstance(bundle, PipelineExecutionBundle)
        self.assertTrue(bundle.success)
        self.assertEqual(bundle.total_stages, 10)
        self.assertEqual(bundle.stages_completed, 10)
        self.assertTrue(bundle.pipeline_id.startswith("pipe-pi-"))
        self.assertTrue(bundle.composite_digest.startswith("sha256:"))

        # Verify all stage results
        for stage in bundle.stage_results:
            self.assertEqual(stage.status, "SUCCEEDED")
            self.assertGreaterEqual(stage.duration_ms, 0.0)
            self.assertTrue(stage.content_hash.startswith("sha256:"))
            self.assertIsInstance(stage.output_summary, dict)


if __name__ == "__main__":
    unittest.main()
