from __future__ import annotations

from dataclasses import dataclass
import hashlib
import unittest

from elmos_project_intelligence.canonical import canonical_digest, canonical_value
from elmos_project_intelligence.task_execution.subsystem_pipelines import (
    PIPELINE_STAGES,
    StageAdapterDescriptor,
    StageAdapterRegistry,
    SubsystemPipelineOrchestrator,
)


def sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


@dataclass
class Adapter:
    descriptor: StageAdapterDescriptor
    malformed: bool = False

    def execute(self, request):
        output = {"stage": self.descriptor.stage_name, "input": request["previous_output_digest"]}
        if self.malformed:
            return {"state": "SUCCEEDED"}
        return {
            "state": "SUCCEEDED",
            "output": output,
            "output_digest": canonical_digest(canonical_value(output)),
            "cost_evidence_status": "ESTIMATED",
        }


def registry(*, malformed_stage: str | None = None) -> StageAdapterRegistry:
    return StageAdapterRegistry(
        [
            Adapter(
                StageAdapterDescriptor(
                    stage,
                    f"adapter.{stage}",
                    "1.0",
                    sha(stage),
                    "BOUNDED_LOCAL",
                ),
                malformed=stage == malformed_stage,
            )
            for stage in PIPELINE_STAGES
        ]
    )


def run(orchestrator: SubsystemPipelineOrchestrator):
    return orchestrator.run_full_analysis_pipeline(
        pipeline_id="pipeline-a",
        tenant_id="tenant-a",
        project_id="project-a",
        revision="abc123",
        input_artifacts={"snapshot_digest": sha("snapshot")},
    )


class TestSubsystemPipelines(unittest.TestCase):
    def test_missing_adapter_is_not_run(self) -> None:
        bundle = run(SubsystemPipelineOrchestrator())
        self.assertFalse(bundle.success)
        self.assertEqual(bundle.stages_completed, 0)
        self.assertEqual(bundle.stage_results[0].status, "NOT_RUN")
        self.assertEqual(bundle.external_evidence_status, "NOT_RUN")

    def test_all_exact_adapters_execute_without_certification_claim(self) -> None:
        bundle = run(SubsystemPipelineOrchestrator(registry()))
        self.assertTrue(bundle.success)
        self.assertEqual(bundle.stages_completed, 10)
        self.assertEqual({item.status for item in bundle.stage_results}, {"SUCCEEDED"})
        self.assertEqual(bundle.independent_evidence_status, "NOT_RUN")
        self.assertEqual(bundle.certification_status, "NOT_CERTIFIED")

    def test_malformed_adapter_result_is_unknown_and_stops_pipeline(self) -> None:
        bundle = run(
            SubsystemPipelineOrchestrator(registry(malformed_stage=PIPELINE_STAGES[2]))
        )
        self.assertFalse(bundle.success)
        self.assertEqual(bundle.stage_results[2].status, "UNKNOWN")
        self.assertTrue(bundle.stage_results[2].blocker.startswith("ADAPTER_RESULT_UNRECONCILED"))
        self.assertEqual(bundle.stage_results[3].status, "NOT_RUN")


if __name__ == "__main__":
    unittest.main()
