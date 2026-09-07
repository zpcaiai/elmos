from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field

from .contracts import ContractModel


class ProjectPath(StrEnum):
    WEB = "WEB"
    DATA_PIPELINE = "DATA_PIPELINE"
    AI_ML = "AI_ML"
    GENERAL = "GENERAL"


class ReproducibilityStatus(StrEnum):
    BITWISE_REPRODUCIBLE = "BITWISE_REPRODUCIBLE"
    DEPENDENCY_REPRODUCIBLE = "DEPENDENCY_REPRODUCIBLE"
    FUNCTIONALLY_REPRODUCIBLE = "FUNCTIONALLY_REPRODUCIBLE"
    PARTIALLY_REPRODUCIBLE = "PARTIALLY_REPRODUCIBLE"
    UNREPRODUCIBLE = "UNREPRODUCIBLE"


class PythonVersionEvidence(ContractModel):
    kind: str
    value: str
    source: str
    confidence: str


class ProjectRoot(ContractModel):
    project_id: str
    relative_path: str
    project_type: str
    manifests: list[str]
    paths: list[ProjectPath]


class ProjectInventory(ContractModel):
    workspace_ref: str
    projects: list[ProjectRoot]
    python_versions: list[PythonVersionEvidence]
    entry_points: list[dict[str, str]]
    dependency_managers: list[str]
    frameworks: list[str]
    notebooks: list[str]
    system_dependencies: list[str]
    index_sources: list[str]
    findings: list[str]
    excluded_paths: list[str]


class Distribution(ContractModel):
    name: str
    version: str
    artifact_hash: str | None = None
    marker: str | None = None


class EnvironmentSnapshot(ContractModel):
    python_version: str
    implementation: str
    platform: dict[str, str]
    abi: str
    distributions: list[Distribution]
    lock_files: list[str]
    native_libraries: list[str]
    environment_keys: list[str]
    reproducibility_status: ReproducibilityStatus
    reproduction_definition: str
    findings: list[str]


class SemanticSymbol(ContractModel):
    symbol_id: str
    module: str
    qualified_name: str
    kind: str
    line: int


class SemanticEdge(ContractModel):
    source_id: str
    target: str
    kind: str
    confidence: str


class SemanticGraph(ContractModel):
    cst_parser: str
    ast_parser: str
    symbols: list[SemanticSymbol]
    edges: list[SemanticEdge]
    type_results: list[dict[str, Any]]
    runtime_observations: list[dict[str, Any]]
    dynamic_findings: list[str]
    parse_failures: list[str]
    generated_files: list[str]


class MigrationStep(ContractModel):
    step_id: str
    step_type: str
    project_ids: list[str]
    executor_policy: dict[str, Any]
    depends_on: list[str]
    validations: list[str]
    blockers: list[str] = Field(default_factory=list)


class TargetProfile(ContractModel):
    profile_type: str
    path: ProjectPath
    python_version: str
    packaging: str
    framework_targets: dict[str, str]
    platform: str
    runner_profile: str
    compatibility_snapshot: str
    constraints: list[str]


class MigrationPlan(ContractModel):
    plan_id: str
    profiles: list[TargetProfile]
    steps: list[MigrationStep]
    blockers: list[str]
    risks: list[str]
    acceptance_gates: list[str]


class EvidenceExtension(ContractModel):
    schema_name: str = Field(default="elmos.python-evidence.v1", alias="schema")
    language: str = "PYTHON"
    organization_id: str
    artifact_type: str
    source_ref: str
    status: str
    content_hash: str
    artifact: dict[str, Any]
