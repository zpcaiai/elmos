"""SCM models and data structures for GitHub and GitLab PR self-healing closed-loop operations.

Covers webhook events, pull requests, merge requests, CI statuses, failure traces,
inline review comments, and repair decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import json
from typing import Any, Mapping, Sequence


class SCMProvider(StrEnum):
    GITHUB = "github"
    GITLAB = "gitlab"


class CIEventKind(StrEnum):
    PULL_REQUEST = "pull_request"
    MERGE_REQUEST = "merge_request"
    CHECK_RUN = "check_run"
    WORKFLOW_RUN = "workflow_run"
    PIPELINE = "pipeline"
    JOB = "job"
    PUSH = "push"
    COMMENT = "comment"


class FailureCategory(StrEnum):
    SYNTAX_ERROR = "syntax_error"
    IMPORT_OR_SYMBOL_ERROR = "import_or_symbol_error"
    TYPE_MISMATCH = "type_mismatch"
    ASSERTION_FAILURE = "assertion_failure"
    RUNTIME_EXCEPTION = "runtime_exception"
    FLAKY_OR_TIMEOUT = "flaky_or_timeout"
    ENVIRONMENT_OR_CONFIG = "environment_or_config"
    SPECIFICATION_DRIFT = "specification_drift"
    RACE_CONDITION = "race_condition"
    DEADLOCK = "deadlock"
    DISTRIBUTED_LOCK_FAILURE = "distributed_lock_failure"
    DATABASE_DEADLOCK = "database_deadlock"
    ASYNC_TIMING = "async_timing"
    UNKNOWN = "unknown"


class RepairStrategy(StrEnum):
    SAFE_CODE_FIX = "safe_code_fix"
    TEST_SELF_HEAL = "test_self_heal"
    COMBINED_REPAIR = "combined_repair"
    MANUAL_INSPECTION_REQUIRED = "manual_inspection_required"


class PRSelfHealingState(StrEnum):
    INITIALIZED = "INITIALIZED"
    EVENT_INGESTED = "EVENT_INGESTED"
    LOGS_PARSED = "LOGS_PARSED"
    DEFECT_TRIAGED = "DEFECT_TRIAGED"
    REPAIR_PLANNED = "REPAIR_PLANNED"
    PATCH_SYNTHESIZED = "PATCH_SYNTHESIZED"
    SANDBOX_VERIFIED = "SANDBOX_VERIFIED"
    BRANCH_PUSHED = "BRANCH_PUSHED"
    PR_CREATED_OR_UPDATED = "PR_CREATED_OR_UPDATED"
    COMMENTS_POSTED = "COMMENTS_POSTED"
    STATUS_UPDATED = "STATUS_UPDATED"
    AUTO_MERGED = "AUTO_MERGED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class WebhookSignatureValidationResult:
    valid: bool
    provider: SCMProvider
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    event_id: str
    provider: SCMProvider
    event_kind: CIEventKind
    repository_owner: str
    repository_name: str
    repository_url: str
    ref: str
    commit_sha: str
    sender: str
    raw_payload: Mapping[str, Any]
    pull_request_id: int | None = None
    merge_request_iid: int | None = None
    target_branch: str = "main"
    source_branch: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ParsedLogDiagnostic:
    file_path: str
    line_number: int | None
    column_number: int | None
    error_code: str
    message: str
    context_snippet: str
    severity: str = "ERROR"


@dataclass(frozen=True, slots=True)
class FailureTrace:
    test_id: str
    test_file: str
    test_function: str
    failure_category: FailureCategory
    exception_class: str
    error_message: str
    stack_trace: Sequence[str]
    assertion_expected: str | None = None
    assertion_actual: str | None = None
    diagnostics: Sequence[ParsedLogDiagnostic] = ()
    raw_log_snippet: str = ""


@dataclass(frozen=True, slots=True)
class DefectClassification:
    category: FailureCategory
    primary_file: str
    primary_line: int | None
    is_test_failure_only: bool
    is_spec_drift: bool
    confidence_score: float
    affected_symbols: Sequence[str]
    recommended_strategy: RepairStrategy
    explanation: str


@dataclass(frozen=True, slots=True)
class PatchProposal:
    file_path: str
    original_content: str
    patched_content: str
    diff: str
    content_sha256: str
    patch_sha256: str
    changes_count: int
    is_test_file: bool


@dataclass(frozen=True, slots=True)
class SandboxedVerificationReceipt:
    run_id: str
    verified: bool
    tests_passed: int
    tests_failed: int
    execution_time_seconds: float
    stdout: str
    stderr: str
    merkle_root_sha256: str
    verification_hash: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class InlineComment:
    path: str
    line: int
    body: str
    side: str = "RIGHT"
    start_line: int | None = None


@dataclass(frozen=True, slots=True)
class PullRequestInfo:
    number: int
    title: str
    body: str
    html_url: str
    head_branch: str
    base_branch: str
    state: str
    is_draft: bool
    labels: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class MergeRequestInfo:
    iid: int
    id: int
    title: str
    description: str
    web_url: str
    source_branch: str
    target_branch: str
    state: str
    labels: Sequence[str] = ()


@dataclass(frozen=True, slots=True)
class PRSelfHealingSession:
    session_id: str
    tenant_id: str
    project_id: str
    provider: SCMProvider
    repo_owner: str
    repo_name: str
    source_ref: str
    target_ref: str
    state: PRSelfHealingState
    failure_traces: Sequence[FailureTrace] = ()
    defect_classification: DefectClassification | None = None
    patches: Sequence[PatchProposal] = ()
    verification_receipt: SandboxedVerificationReceipt | None = None
    pr_info: PullRequestInfo | None = None
    mr_info: MergeRequestInfo | None = None
    fix_branch_name: str = ""
    commit_sha: str = ""
    error_message: str | None = None
    audit_events: Sequence[Mapping[str, Any]] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
