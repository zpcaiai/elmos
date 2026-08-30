"""Fail-closed facade for the Knowledge-Skill-Model Foundry runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .adapters import AdapterRegistry, InvocationPermit
from .artifacts import ContentAddressedArtifactStore
from .authorizations import AuthorizationVerifier
from .database import DatabaseManager
from .dataset import DatasetFoundry
from .domain import ExecutionResult, TenantScope
from .evidence import EvidenceLedger
from .kernel import ExecutionKernel
from .knowledge import KnowledgeManager
from .memory import ExperienceMemoryStore
from .model import ModelFoundry
from .pipelines import PipelineOrchestrator
from .policies import PolicyEngine
from .serving import ModelServingGateway
from .skills import SkillCatalog
from .store import FoundryStore


class FoundryService:
    """Top-level service with exact catalog and adapter dependency injection."""

    def __init__(
        self,
        *,
        kernel: ExecutionKernel | None = None,
        catalog_path: Path | None = None,
        adapter_registry: AdapterRegistry | None = None,
        store: FoundryStore | None = None,
        artifact_store: ContentAddressedArtifactStore | None = None,
        knowledge_consent_verifier: AuthorizationVerifier | None = None,
        experience_capture_verifier: AuthorizationVerifier | None = None,
        dataset_data_use_verifier: AuthorizationVerifier | None = None,
        model_promotion_verifier: AuthorizationVerifier | None = None,
        serving_route_verifier: AuthorizationVerifier | None = None,
    ) -> None:
        self.kernel = kernel or ExecutionKernel()
        self.policies = PolicyEngine(self.kernel.require_context)
        self.evidence = EvidenceLedger(
            self.kernel,
            store=store,
            artifact_store=artifact_store,
        )
        self.knowledge = KnowledgeManager(
            self.kernel,
            consent_verifier=knowledge_consent_verifier,
        )
        self.skills = SkillCatalog(
            self.kernel,
            catalog_path=catalog_path,
            adapter_registry=adapter_registry,
            store=store,
        )
        self.memory = ExperienceMemoryStore(
            self.kernel,
            capture_verifier=experience_capture_verifier,
        )
        self.dataset = DatasetFoundry(
            self.kernel,
            data_use_verifier=dataset_data_use_verifier,
        )
        self.model = ModelFoundry(
            self.kernel,
            evidence_ledger=self.evidence,
            policy_engine=self.policies,
            promotion_verifier=model_promotion_verifier,
        )
        self.serving = ModelServingGateway(
            self.kernel,
            route_verifier=serving_route_verifier,
        )
        self.database = DatabaseManager()
        self.pipelines = PipelineOrchestrator(
            kernel=self.kernel,
            knowledge=self.knowledge,
            skills=self.skills,
            memory=self.memory,
            dataset=self.dataset,
            model=self.model,
            serving=self.serving,
            policies=self.policies,
            evidence=self.evidence,
        )

    def execute_skill(
        self,
        skill_name: str,
        inputs: Mapping[str, Any],
        tenant_scope: TenantScope | None = None,
        *,
        adapter_id: str | None = None,
        invocation_id: str | None = None,
        permit: InvocationPermit | None = None,
    ) -> ExecutionResult:
        return self.skills.execute_skill(
            skill_name,
            inputs,
            tenant_scope=tenant_scope,
            adapter_id=adapter_id,
            invocation_id=invocation_id,
            permit=permit,
        )

    def route_meta_skill(
        self,
        meta_skill_name: str,
        query: str = "",
        *,
        filters: Mapping[str, Any] | None = None,
        candidate_limit: int | None = None,
        activation_limit: int | None = None,
    ) -> Sequence[str]:
        return self.skills.route_meta_skill(
            meta_skill_name,
            query=query,
            filters=filters,
            candidate_limit=candidate_limit,
            activation_limit=activation_limit,
        )

    def run_pipeline(
        self,
        pipeline_name: str,
        params: Mapping[str, Any],
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        """Prepare one exact pipeline; never execute provider or deployment effects."""
        return self.pipelines.prepare_pipeline(
            pipeline_name,
            params,
            tenant_scope=tenant_scope,
        )

    def status(self) -> Mapping[str, Any]:
        return self.skills.describe()


__all__ = ["FoundryService"]
