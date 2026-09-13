"""ELMOS Autonomous QA PR Self-Healing Closed Loop.

Provides GitHub and GitLab integration, CI log parsing, defect triage RCA,
safe code auto-repair, test self-healing, and sandboxed verification.
"""

from .ci_log_parser import CILogParser
from .defect_triage_rca import DefectTriageRCA
from .github_client import GitHubClient, MockGitHubTransport
from .gitlab_client import GitLabClient, MockGitLabTransport
from .pr_self_healing_orchestrator import PRSelfHealingOrchestrator
from .safe_code_fixer import PatchSafetyViolation, SafeCodeFixer
from .sandboxed_verifier import SandboxedVerifier
from .scm_models import (
    CIEventKind,
    DefectClassification,
    FailureCategory,
    FailureTrace,
    InlineComment,
    MergeRequestInfo,
    PatchProposal,
    PRSelfHealingSession,
    PRSelfHealingState,
    PullRequestInfo,
    RepairStrategy,
    SandboxedVerificationReceipt,
    SCMProvider,
    WebhookEvent,
    WebhookSignatureValidationResult,
)
from .test_self_healer import TestSelfHealer

__all__ = [
    "CILogParser",
    "DefectTriageRCA",
    "GitHubClient",
    "GitLabClient",
    "MockGitHubTransport",
    "MockGitLabTransport",
    "PRSelfHealingOrchestrator",
    "PatchSafetyViolation",
    "SafeCodeFixer",
    "SandboxedVerifier",
    "TestSelfHealer",
    "CIEventKind",
    "DefectClassification",
    "FailureCategory",
    "FailureTrace",
    "InlineComment",
    "MergeRequestInfo",
    "PatchProposal",
    "PRSelfHealingSession",
    "PRSelfHealingState",
    "PullRequestInfo",
    "RepairStrategy",
    "SandboxedVerificationReceipt",
    "SCMProvider",
    "WebhookEvent",
    "WebhookSignatureValidationResult",
]
