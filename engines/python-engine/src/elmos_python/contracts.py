from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ContractModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class JobStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ErrorCode(StrEnum):
    PYTHON_PROJECT_NOT_FOUND = "PYTHON_PROJECT_NOT_FOUND"
    PYTHON_MULTIPLE_PROJECT_ROOTS = "PYTHON_MULTIPLE_PROJECT_ROOTS"
    PYTHON_INTERPRETER_UNAVAILABLE = "PYTHON_INTERPRETER_UNAVAILABLE"
    PYTHON_VERSION_UNRESOLVED = "PYTHON_VERSION_UNRESOLVED"
    PYTHON_ENVIRONMENT_UNREPRODUCIBLE = "PYTHON_ENVIRONMENT_UNREPRODUCIBLE"
    PYTHON_DEPENDENCY_RESOLUTION_FAILED = "PYTHON_DEPENDENCY_RESOLUTION_FAILED"
    PYTHON_WHEEL_UNAVAILABLE = "PYTHON_WHEEL_UNAVAILABLE"
    PYTHON_NATIVE_LIBRARY_MISSING = "PYTHON_NATIVE_LIBRARY_MISSING"
    PYTHON_CST_PARSE_FAILED = "PYTHON_CST_PARSE_FAILED"
    PYTHON_TYPE_ANALYSIS_INCOMPLETE = "PYTHON_TYPE_ANALYSIS_INCOMPLETE"
    PYTHON_RUNTIME_TRACE_FAILED = "PYTHON_RUNTIME_TRACE_FAILED"
    GPU_RUNNER_REQUIRED = "GPU_RUNNER_REQUIRED"
    LEGACY_PYTHON_RUNNER_REQUIRED = "LEGACY_PYTHON_RUNNER_REQUIRED"
    NOTEBOOK_STATE_UNRESOLVED = "NOTEBOOK_STATE_UNRESOLVED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INTERNAL_ENGINE_ERROR = "INTERNAL_ENGINE_ERROR"


class ExecutorType(StrEnum):
    LIBCST = "LIBCST"
    PYTHON_AST = "PYTHON_AST"
    UV = "UV"
    PIP = "PIP"
    CONDA = "CONDA"
    MYPY = "MYPY"
    PYRIGHT = "PYRIGHT"
    PYTEST = "PYTEST"
    CODING_AGENT = "CODING_AGENT"
    DATA_VALIDATOR = "DATA_VALIDATOR"
    MODEL_VALIDATOR = "MODEL_VALIDATOR"
    HUMAN = "HUMAN"


class Capabilities(ContractModel):
    schema_version: str = "1.0"
    engine: str = "ELMOS_PYTHON"
    engine_version: str = "1.0.0"
    languages: list[str] = ["PYTHON"]
    source_versions: list[str]
    supported_target_versions: list[str]
    project_models: list[str]
    frameworks: list[str]
    runner_profiles: list[str]
    validation_capabilities: list[str]
    sandbox_requirements: dict[str, Any]


class JobRequest(ContractModel):
    organization_id: str = Field(min_length=1)
    repository_snapshot_ref: str = Field(min_length=1)
    workspace_ref: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class StepDefinition(ContractModel):
    step_id: str = Field(min_length=1)
    executor_type: ExecutorType
    configuration: dict[str, Any] = Field(default_factory=dict)


class ExecutionBudget(ContractModel):
    timeout_seconds: int = Field(ge=1)
    cpu_seconds: int = Field(ge=1)
    max_bytes_written: int = Field(ge=0)
    max_agent_credits: int = Field(ge=0)


class ExecuteStepRequest(ContractModel):
    organization_id: str = Field(min_length=1)
    migration_run_id: str = Field(min_length=1)
    migration_plan_version: int = Field(ge=1)
    step_definition: StepDefinition
    workspace_ref: str = Field(min_length=1)
    source_commit: str = Field(min_length=1)
    execution_budget: ExecutionBudget
    policy: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class EngineError(ContractModel):
    error_code: ErrorCode
    message: str
    retryable: bool = False
    evidence_refs: list[str] = Field(default_factory=list)
    failed_command: str | None = None
    sanitized_log_ref: str | None = None
    suggested_action: str


class JobResponse(ContractModel):
    schema_version: str = "1.0"
    job_id: str
    status: JobStatus
    evidence_refs: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    error: EngineError | None = None
