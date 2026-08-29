"""Unified Foundry Service orchestrating all commercial capability layers for Elmos Foundry.

Combines knowledge ingestion, skill execution, experience memory, dataset creation,
model release packaging, serving gateway, policies, and evidence ledgers.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .database import DatabaseManager
from .dataset import DatasetFoundry
from .domain import (
    ConsentStatus,
    ExecutionResult,
    GateLevel,
    LifecycleState,
    RightsClass,
    TenantScope,
)
from .evidence import EvidenceLedger
from .kernel import ExecutionKernel
from .knowledge import KnowledgeManager
from .memory import ExperienceMemoryStore
from .model import ModelFoundry
from .pipelines import PipelineOrchestrator
from .policies import PolicyEngine
from .serving import ModelServingGateway
from .skills import SkillCatalog


class FoundryService:
    """Top-level enterprise service orchestrator for the Knowledge-Skill-Model Foundry."""

    def __init__(self) -> None:
        self.kernel = ExecutionKernel()
        self.knowledge = KnowledgeManager(self.kernel)
        self.skills = SkillCatalog(self.kernel)
        self.memory = ExperienceMemoryStore(self.kernel)
        self.dataset = DatasetFoundry(self.kernel)
        self.model = ModelFoundry(self.kernel)
        self.serving = ModelServingGateway(self.kernel)
        self.policies = PolicyEngine()
        self.evidence = EvidenceLedger(self.kernel)
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
    ) -> ExecutionResult:
        return self.skills.execute_skill(skill_name, inputs, tenant_scope=tenant_scope)

    def route_meta_skill(self, meta_skill_name: str, query: str = "") -> Sequence[str]:
        return self.skills.route_meta_skill(meta_skill_name, query=query)

    def run_pipeline(
        self,
        pipeline_name: str,
        params: Mapping[str, Any],
        tenant_scope: TenantScope | None = None,
    ) -> Mapping[str, Any]:
        """Execute one of the four lifecycle pipelines by name."""
        if pipeline_name == "knowledge-to-skill":
            return self.pipelines.run_knowledge_to_skill_pipeline(
                source_id=params.get("source_id", "src-01"),
                document_text=params.get("document_text", "Sample specification text"),
                skill_name=params.get("skill_name", "elmos-custom-skill"),
                tenant_scope=tenant_scope,
            )
        elif pipeline_name == "experience-to-dataset":
            return self.pipelines.run_experience_to_dataset_pipeline(
                dataset_name=params.get("dataset_name", "foundry-ds"),
                task_type=params.get("task_type"),
                tenant_scope=tenant_scope,
            )
        elif pipeline_name == "train-certify-deploy":
            return self.pipelines.run_train_certify_deploy_pipeline(
                base_model=params.get("base_model", "qwen2.5-coder-32b"),
                adapter_name=params.get("adapter_name", "refactor-adapter"),
                dataset_id=params.get("dataset_id", "ds-01"),
                skill_set=params.get("skill_set", ["00-foundation-contracts"]),
                tenant_scope=tenant_scope,
            )
        elif pipeline_name == "customer-private-adapter":
            return self.pipelines.run_customer_private_adapter_pipeline(
                base_model=params.get("base_model", "deepseek-v3"),
                adapter_name=params.get("adapter_name", "cust-fintech-adapter"),
                customer_docs=params.get("customer_docs", ["Customer domain rules"]),
                tenant_scope=tenant_scope,
            )
        else:
            raise ValueError(f"Unknown pipeline: {pipeline_name}")
