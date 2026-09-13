"""Exact host-adapter orchestration for the Project Intelligence pipeline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol

from ..canonical import canonical_digest, canonical_value, validate_digest


PIPELINE_STAGES = (
    "source-ingestion",
    "framework-fingerprint",
    "dependency-analysis",
    "symbol-and-type-index",
    "control-flow-analysis",
    "dataflow-and-taint-analysis",
    "architecture-and-drift-analysis",
    "threat-and-risk-analysis",
    "cost-and-debt-analysis",
    "artifact-and-evidence-generation",
)


@dataclass(frozen=True, slots=True)
class StageAdapterDescriptor:
    stage_name: str
    adapter_id: str
    adapter_version: str
    attestation_digest: str
    effect_class: str

    def __post_init__(self) -> None:
        if self.stage_name not in PIPELINE_STAGES:
            raise ValueError("adapter stage is not allowlisted")
        if not self.adapter_id or not self.adapter_version:
            raise ValueError("adapter identity is incomplete")
        validate_digest(self.attestation_digest)
        if self.effect_class not in {"BOUNDED_LOCAL", "HOST_EXTERNAL"}:
            raise ValueError("adapter effect class is unsupported")


class PipelineStageAdapter(Protocol):
    descriptor: StageAdapterDescriptor

    def execute(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class StageAdapterRegistry:
    def __init__(self, adapters: Sequence[PipelineStageAdapter] = ()) -> None:
        values: dict[str, PipelineStageAdapter] = {}
        for adapter in adapters:
            descriptor = getattr(adapter, "descriptor", None)
            if not isinstance(descriptor, StageAdapterDescriptor):
                raise TypeError("pipeline adapter descriptor is required")
            if descriptor.stage_name in values:
                raise ValueError("pipeline stage adapter is duplicated")
            values[descriptor.stage_name] = adapter
        self._adapters = MappingProxyType(values)

    def resolve(self, stage_name: str) -> PipelineStageAdapter | None:
        return self._adapters.get(stage_name)


@dataclass(frozen=True, slots=True)
class PipelineStageResult:
    stage_name: str
    status: str
    adapter_id: str | None
    output_digest: str | None
    cost_evidence_status: str
    blocker: str | None


@dataclass(frozen=True, slots=True)
class PipelineExecutionBundle:
    pipeline_id: str
    tenant_id: str
    project_id: str
    revision: str
    total_stages: int
    stages_completed: int
    success: bool
    stage_results: tuple[PipelineStageResult, ...]
    composite_digest: str
    external_evidence_status: str
    independent_evidence_status: str
    certification_status: str


class SubsystemPipelineOrchestrator:
    """Execute ten exact stages; missing or malformed adapters fail closed."""

    def __init__(self, registry: StageAdapterRegistry | None = None) -> None:
        self.registry = registry or StageAdapterRegistry()

    @staticmethod
    def _validate_result(
        stage_name: str, adapter: PipelineStageAdapter, value: Mapping[str, Any]
    ) -> tuple[str, str, str]:
        if not isinstance(value, Mapping) or set(value) != {
            "state",
            "output",
            "output_digest",
            "cost_evidence_status",
        }:
            raise ValueError("pipeline adapter result fields are not exact")
        state = value["state"]
        if state not in {"SUCCEEDED", "PARTIAL", "BLOCKED", "FAILED", "UNKNOWN"}:
            raise ValueError("pipeline adapter returned an unsupported state")
        output = value["output"]
        observed = canonical_digest(canonical_value(output))
        if value["output_digest"] != observed:
            raise ValueError("pipeline adapter output digest drifted")
        cost_state = value["cost_evidence_status"]
        if cost_state not in {"NOT_RUN", "ESTIMATED", "PROVIDER_RECEIPT_VERIFIED"}:
            raise ValueError("pipeline cost evidence state is unsupported")
        if (
            cost_state == "PROVIDER_RECEIPT_VERIFIED"
            and adapter.descriptor.effect_class != "HOST_EXTERNAL"
        ):
            raise ValueError("local adapter cannot verify provider cost")
        if adapter.descriptor.stage_name != stage_name:
            raise ValueError("pipeline adapter stage identity drifted")
        return str(state), observed, str(cost_state)

    def run_full_analysis_pipeline(
        self,
        *,
        pipeline_id: str,
        tenant_id: str,
        project_id: str,
        revision: str,
        input_artifacts: Mapping[str, Any],
    ) -> PipelineExecutionBundle:
        if not all((pipeline_id, tenant_id, project_id, revision)):
            raise ValueError("pipeline scope is incomplete")
        previous_digest = canonical_digest(canonical_value(dict(input_artifacts)))
        results: list[PipelineStageResult] = []
        upstream_blocked = False
        for stage_name in PIPELINE_STAGES:
            adapter = self.registry.resolve(stage_name)
            if upstream_blocked:
                results.append(PipelineStageResult(stage_name, "NOT_RUN", None, None, "NOT_RUN", "UPSTREAM_STAGE_INCOMPLETE"))
                continue
            if adapter is None:
                results.append(PipelineStageResult(stage_name, "NOT_RUN", None, None, "NOT_RUN", "EXACT_STAGE_ADAPTER_NOT_CONFIGURED"))
                upstream_blocked = True
                continue
            request = {
                "schema_version": "elmos.project-intelligence.pipeline-stage-request.v1",
                "pipeline_id": pipeline_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "revision": revision,
                "stage_name": stage_name,
                "previous_output_digest": previous_digest,
                "adapter_attestation_digest": adapter.descriptor.attestation_digest,
            }
            try:
                raw = adapter.execute(request)
                state, output_digest, cost_state = self._validate_result(stage_name, adapter, raw)
                blocker = None if state == "SUCCEEDED" else f"STAGE_{state}"
            except Exception as exc:
                state, output_digest, cost_state = "UNKNOWN", None, "NOT_RUN"
                blocker = f"ADAPTER_RESULT_UNRECONCILED:{type(exc).__name__}"
            results.append(
                PipelineStageResult(
                    stage_name,
                    state,
                    adapter.descriptor.adapter_id,
                    output_digest,
                    cost_state,
                    blocker,
                )
            )
            if state != "SUCCEEDED":
                upstream_blocked = True
            else:
                assert output_digest is not None
                previous_digest = output_digest
        completed = sum(item.status == "SUCCEEDED" for item in results)
        document = [
            {
                "stage_name": item.stage_name,
                "status": item.status,
                "adapter_id": item.adapter_id,
                "output_digest": item.output_digest,
                "cost_evidence_status": item.cost_evidence_status,
                "blocker": item.blocker,
            }
            for item in results
        ]
        return PipelineExecutionBundle(
            pipeline_id=pipeline_id,
            tenant_id=tenant_id,
            project_id=project_id,
            revision=revision,
            total_stages=len(PIPELINE_STAGES),
            stages_completed=completed,
            success=completed == len(PIPELINE_STAGES),
            stage_results=tuple(results),
            composite_digest=canonical_digest(canonical_value(document)),
            external_evidence_status="NOT_RUN",
            independent_evidence_status="NOT_RUN",
            certification_status="NOT_CERTIFIED",
        )
