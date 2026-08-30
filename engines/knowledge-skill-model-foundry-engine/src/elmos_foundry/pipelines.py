"""Deterministic prepare-only plans for the exact 14 Foundry pipelines.

No method in this module ingests data, creates datasets, trains models, signs
evidence, deploys artifacts, or promotes certification. Source pipeline YAML
is provenance-bound declarative input only.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .dataset import DatasetFoundry
from .domain import TenantScope
from .evidence import EvidenceLedger
from .handlers import (
    CERTIFICATION_STATUS,
    EXTERNAL_EVIDENCE_STATUS,
    LOCAL_EVIDENCE_STATUS,
    MAXIMUM_LOCAL_DECISION,
    canonical_json,
    digest_json,
)
from .kernel import ExecutionKernel
from .knowledge import KnowledgeManager
from .memory import ExperienceMemoryStore
from .model import ModelFoundry
from .policies import PolicyEngine
from .serving import ModelServingGateway
from .skills import EXPECTED_PIPELINES, SkillCatalog


@dataclass(frozen=True, slots=True)
class PipelineProfile:
    name: str
    required_inputs: tuple[str, ...]
    required_adapters: tuple[str, ...]
    external_effects: tuple[str, ...]


def _profile(
    name: str,
    required_inputs: tuple[str, ...],
    required_adapters: tuple[str, ...],
    external_effects: tuple[str, ...],
) -> PipelineProfile:
    return PipelineProfile(name, required_inputs, required_adapters, external_effects)


_PIPELINE_PROFILES = (
    _profile("knowledge-to-skill", ("source_id", "document_text", "skill_name"), ("knowledge-ingestion", "sandbox-replay", "independent-verifier"), ("knowledge-write", "skill-publication")),
    _profile("experience-to-dataset", ("dataset_name",), ("durable-experience-store", "dataset-builder", "privacy-verifier"), ("dataset-write",)),
    _profile("train-certify-deploy", ("base_model", "adapter_name", "dataset_id", "skill_set"), ("training-provider", "independent-evaluator", "deployment-provider"), ("model-training", "artifact-publication", "deployment")),
    _profile("customer-private-adapter", ("base_model", "adapter_name", "customer_docs"), ("private-training-provider", "tenant-isolation-verifier", "deployment-provider"), ("customer-data-processing", "model-training", "deployment")),
    _profile("capability-gap-to-skill", ("gap_id", "acceptance_criteria"), ("gap-analyzer", "sandbox-replay", "independent-verifier"), ("skill-publication",)),
    _profile("repository-task-intake-to-certify", ("repository_revision", "task_contract"), ("repository-provider", "sandbox-runner", "independent-verifier"), ("repository-read", "sandbox-execution", "artifact-publication")),
    _profile("spring-modernization-golden-route", ("source_version", "target_version", "repository_revision"), ("spring-toolchain", "sandbox-runner", "independent-verifier"), ("repository-read", "sandbox-execution")),
    _profile("cross-language-golden-route", ("source_language", "target_language", "repository_revision"), ("source-toolchain", "target-toolchain", "differential-verifier"), ("repository-read", "sandbox-execution")),
    _profile("database-zero-downtime-golden-route", ("source_engine", "target_engine", "schema_digest"), ("source-database", "target-database", "reconciliation-verifier"), ("database-read", "database-write", "cutover")),
    _profile("project-generation-golden-route", ("project_contract", "target_stack"), ("target-toolchain", "sandbox-runner", "independent-verifier"), ("artifact-write", "sandbox-execution")),
    _profile("frontend-miniapp-golden-route", ("source_revision", "target_profile"), ("source-browser", "target-device", "visual-accessibility-verifier"), ("repository-read", "device-execution", "artifact-publication")),
    _profile("data-platform-golden-route", ("source_platform", "target_platform", "data_contract"), ("source-data-platform", "target-data-platform", "reconciliation-verifier"), ("data-read", "data-write", "cutover")),
    _profile("ai-agent-rag-golden-route", ("knowledge_snapshot", "model_profile", "evaluation_contract"), ("retrieval-provider", "model-provider", "independent-evaluator"), ("provider-inference", "evaluation-execution")),
    _profile("customer-delivery-lifecycle", ("artifact_digest", "customer_acceptance_contract"), ("artifact-store", "delivery-provider", "customer-verifier"), ("artifact-publication", "customer-delivery", "release")),
)

PIPELINE_PROFILE_REGISTRY: Mapping[str, PipelineProfile] = MappingProxyType(
    {profile.name: profile for profile in _PIPELINE_PROFILES}
)
if set(PIPELINE_PROFILE_REGISTRY) != EXPECTED_PIPELINES:
    raise RuntimeError("the exact 14-pipeline preparation registry is incomplete")


class PipelineOrchestrator:
    """Prepare content-addressed plans without performing pipeline effects."""

    def __init__(
        self,
        kernel: ExecutionKernel,
        knowledge: KnowledgeManager,
        skills: SkillCatalog,
        memory: ExperienceMemoryStore,
        dataset: DatasetFoundry,
        model: ModelFoundry,
        serving: ModelServingGateway,
        policies: PolicyEngine,
        evidence: EvidenceLedger,
    ) -> None:
        self.kernel = kernel
        self.skills = skills
        # Kept for API compatibility; preparation never invokes these mutable
        # or evidence-producing collaborators.
        self.knowledge = knowledge
        self.memory = memory
        self.dataset = dataset
        self.model = model
        self.serving = serving
        self.policies = policies
        self.evidence = evidence

    def prepare_pipeline(
        self,
        pipeline_name: str,
        params: Mapping[str, Any],
        *,
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        scope = tenant_scope or self.kernel.current_tenant
        if not isinstance(params, Mapping):
            raise TypeError("pipeline parameters must be an object")
        self.kernel.require_context(scope, "foundry.pipeline.prepare")
        profile = PIPELINE_PROFILE_REGISTRY.get(pipeline_name)
        catalog_record = self.skills.pipeline_records.get(pipeline_name)
        if profile is None or catalog_record is None:
            return MappingProxyType(
                {
                    "pipeline": pipeline_name,
                    "status": "UNKNOWN_PIPELINE",
                    "execution_status": "NOT_RUN",
                    "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
                    "certification_status": CERTIFICATION_STATUS,
                }
            )
        normalized = canonical_json(params)
        if not isinstance(normalized, dict):
            raise TypeError("pipeline parameters must be an object")
        missing = tuple(
            name
            for name in profile.required_inputs
            if name not in normalized or normalized[name] in (None, "", (), [], {})
        )
        plan = {
            "pipeline": pipeline_name,
            "kind": catalog_record["kind"],
            "execution_mode": catalog_record["execution_mode"],
            "source": {"path": catalog_record["source_path"], "sha256": catalog_record["source_sha256"]},
            "catalog_digest": self.skills.snapshot.content_sha256,
            "tenant_scope": {
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "actor_id": scope.actor_id,
                "environment_id": scope.environment_id,
                "workspace_digest": scope.workspace_digest,
                "revision_set_id": scope.revision_set_id,
                "invocation_id": scope.invocation_id,
                "lease_id": scope.lease_id,
                "context_digest": scope.binding_digest,
            },
            "input_digest": digest_json(normalized),
            "provided_input_keys": tuple(sorted(normalized)),
            "required_inputs": profile.required_inputs,
            "missing_required_inputs": missing,
            "required_adapters": profile.required_adapters,
            "external_effects": profile.external_effects,
            "side_effects_authorized": False,
            "execution_status": "NOT_RUN",
            "local_validation_status": (
                "FAILED_SELF_ATTESTED" if missing else "PASSED_SELF_ATTESTED"
            ),
            "local_evidence_status": "NOT_RUN" if missing else LOCAL_EVIDENCE_STATUS,
            "external_evidence_status": EXTERNAL_EVIDENCE_STATUS,
            "certification_status": CERTIFICATION_STATUS,
            "maximum_local_decision": "NOT_READY" if missing else MAXIMUM_LOCAL_DECISION,
            "status": "BLOCKED" if missing else MAXIMUM_LOCAL_DECISION,
        }
        result = dict(plan)
        result["plan_digest"] = digest_json(plan)
        return MappingProxyType(result)

    def run_knowledge_to_skill_pipeline(
        self,
        source_id: str,
        document_text: str,
        skill_name: str,
        pack_name: str = "01-knowledge-ingestion-governance",
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        return self.prepare_pipeline(
            "knowledge-to-skill",
            {"source_id": source_id, "document_text": document_text, "skill_name": skill_name, "pack_name": pack_name},
            tenant_scope=tenant_scope,
        )

    def run_experience_to_dataset_pipeline(
        self,
        dataset_name: str,
        task_type: str | None = None,
        min_reward: float = 0.8,
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        return self.prepare_pipeline(
            "experience-to-dataset",
            {"dataset_name": dataset_name, "task_type": task_type, "min_reward": min_reward},
            tenant_scope=tenant_scope,
        )

    def run_train_certify_deploy_pipeline(
        self,
        base_model: str,
        adapter_name: str,
        dataset_id: str,
        skill_set: Sequence[str],
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        return self.prepare_pipeline(
            "train-certify-deploy",
            {"base_model": base_model, "adapter_name": adapter_name, "dataset_id": dataset_id, "skill_set": list(skill_set)},
            tenant_scope=tenant_scope,
        )

    def run_customer_private_adapter_pipeline(
        self,
        base_model: str,
        adapter_name: str,
        customer_docs: Sequence[str],
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        return self.prepare_pipeline(
            "customer-private-adapter",
            {"base_model": base_model, "adapter_name": adapter_name, "customer_docs": list(customer_docs)},
            tenant_scope=tenant_scope,
        )


__all__ = ["PIPELINE_PROFILE_REGISTRY", "PipelineOrchestrator", "PipelineProfile"]
