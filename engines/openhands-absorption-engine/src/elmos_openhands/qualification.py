"""Executable Golden, load, chaos and independent-security qualification."""

from __future__ import annotations

import sqlite3
import re
import threading
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Callable, Iterable, Mapping, Protocol

from .artifacts import ContentAddressedStore
from .errors import ContractViolation
from .evidence import EvidenceItem
from .models import Identity, canonical_json, digest_of, new_id, utc_now


class CampaignType(StrEnum):
    GOLDEN_REPO = "golden_repo"
    LOAD = "load"
    CHAOS = "chaos"
    SECURITY_REVIEW = "security_review"
    PROVIDER_CONFORMANCE = "provider_conformance"
    BROWSER_DEVICE = "browser_device"
    POSTGRES_TEMPORAL = "postgres_temporal"
    PRODUCTION_SANDBOX = "production_sandbox"


@dataclass(frozen=True, slots=True)
class QualificationTarget:
    target_id: str
    target_digest: str
    environment_digest: str
    requirements: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.target_id or re.fullmatch(r"sha256:[0-9a-f]{64}", self.target_digest) is None or re.fullmatch(r"sha256:[0-9a-f]{64}", self.environment_digest) is None:
            raise ContractViolation("qualification target must be digest-bound")


@dataclass(frozen=True, slots=True)
class GoldenRepository:
    repository_id: str
    commit_digest: str
    loc: int
    language_profile: tuple[str, ...]
    task_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.repository_id or not self.commit_digest.startswith("sha256:") or self.loc <= 0 or not self.task_refs:
            raise ContractViolation("golden repository contract is invalid")


class GoldenSuiteValidator:
    def validate(self, repositories: Iterable[GoldenRepository]) -> tuple[GoldenRepository, ...]:
        values = tuple(repositories)
        if len({repo.repository_id for repo in values}) != len(values):
            raise ContractViolation("golden repository identities must be unique")
        if sum(repo.loc > 500_000 for repo in values) < 3 or not any(repo.loc > 1_000_000 for repo in values):
            raise ContractViolation("golden suite requires three >500k LOC repos and one >1M LOC repo")
        return values


@dataclass(frozen=True, slots=True)
class CampaignOutput:
    status: str
    raw_evidence: Mapping[str, bytes]
    metrics: Mapping[str, float | int | str]
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"PASS", "FAIL", "BLOCKED", "INCONCLUSIVE"} or not self.raw_evidence:
            raise ContractViolation("campaign output must include status and raw evidence")


class CampaignExecutor(Protocol):
    executor_id: str
    independent: bool

    def execute(self, campaign_type: CampaignType, target: QualificationTarget, authorization_ref: str) -> CampaignOutput: ...


@dataclass(frozen=True, slots=True)
class QualificationResult:
    qualification_id: str
    identity: Identity
    campaign_type: CampaignType
    target: QualificationTarget
    status: str
    executor_id: str | None
    independent_verifier_id: str | None
    authorization_ref: str | None
    evidence: tuple[EvidenceItem, ...]
    metrics: Mapping[str, Any]
    findings: tuple[str, ...]
    created_at: str
    decision: str

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "identity": {"tenant_id": self.identity.tenant_id, "project_id": self.identity.project_id, "task_id": self.identity.task_id, "run_id": self.identity.run_id, "node_id": self.identity.node_id}, "campaign_type": self.campaign_type.value, "target": asdict(self.target), "evidence": [item.as_dict() for item in self.evidence], "certification": "NOT_CERTIFIED"}


class QualificationStore:
    def __init__(self, database: str = ":memory:") -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS qualification_results(qualification_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,project_id TEXT NOT NULL,task_id TEXT NOT NULL,run_id TEXT NOT NULL,node_id TEXT NOT NULL,campaign_type TEXT NOT NULL,target_digest TEXT NOT NULL,status TEXT NOT NULL,result_json TEXT NOT NULL,created_at TEXT NOT NULL);
               CREATE INDEX IF NOT EXISTS qualification_results_scope_idx ON qualification_results(tenant_id,project_id,task_id,run_id,node_id,campaign_type,created_at);"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def put(self, result: QualificationResult) -> None:
        encoded = canonical_json(result.as_dict())
        with self._lock:
            existing = self._connection.execute("SELECT tenant_id,project_id,task_id,run_id,node_id,result_json FROM qualification_results WHERE qualification_id=?", (result.qualification_id,)).fetchone()
            if existing is not None:
                if tuple(existing[name] for name in ("tenant_id", "project_id", "task_id", "run_id", "node_id")) != result.identity.scope():
                    raise ContractViolation("qualification identity collision crosses project/task scope")
                if existing["result_json"] != encoded:
                    raise ContractViolation("qualification result is immutable")
            self._connection.execute(
                "INSERT OR IGNORE INTO qualification_results(qualification_id,tenant_id,project_id,task_id,run_id,node_id,campaign_type,target_digest,status,result_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (result.qualification_id, *result.identity.scope(), result.campaign_type.value, result.target.target_digest, result.status, encoded, result.created_at),
            )

    def statuses(self, identity: Identity) -> Mapping[str, str]:
        with self._lock:
            rows = self._connection.execute("SELECT campaign_type,status FROM qualification_results WHERE tenant_id=? AND project_id=? AND task_id=? AND run_id=? AND node_id=? ORDER BY created_at", identity.scope()).fetchall()
        result = {kind.value: "NOT_RUN" for kind in CampaignType}
        result.update({row["campaign_type"]: row["status"] for row in rows})
        return result


class QualificationRunner:
    def __init__(self, store: QualificationStore, artifacts: ContentAddressedStore) -> None:
        self.store, self.artifacts = store, artifacts

    def not_run(self, identity: Identity, campaign_type: CampaignType, target: QualificationTarget, reason: str) -> QualificationResult:
        if not reason:
            raise ContractViolation("NOT_RUN qualification requires a reason")
        created = utc_now()
        qualification_id = "qual_" + digest_of({"identity": identity.scope(), "type": campaign_type.value, "target": target.target_digest, "state": "NOT_RUN"}).split(":", 1)[1]
        result = QualificationResult(qualification_id, identity, campaign_type, target, "NOT_RUN", None, None, None, (), {}, (reason,), created, "NOT_CERTIFIED")
        self.store.put(result)
        return result

    def run(
        self,
        identity: Identity,
        campaign_type: CampaignType,
        target: QualificationTarget,
        *,
        authorization_ref: str,
        executor: CampaignExecutor,
        independent_verifier: Callable[[CampaignOutput], tuple[str, str, tuple[str, ...]]] | None,
        replay_command: tuple[str, ...],
    ) -> QualificationResult:
        if not authorization_ref or not replay_command:
            raise ContractViolation("qualification execution requires authorization and replay command")
        output = executor.execute(campaign_type, target, authorization_ref)
        evidence: list[EvidenceItem] = []
        for role, raw in sorted(output.raw_evidence.items()):
            if not isinstance(raw, bytes):
                raise ContractViolation("campaign raw evidence must be bytes")
            artifact = self.artifacts.put(identity.tenant_id, raw, kind="qualification-" + campaign_type.value, media_type="application/octet-stream")
            evidence.append(EvidenceItem(new_id(), role, output.status, artifact, campaign_type.value, executor.executor_id, target.environment_digest, replay_command))
        verifier_id: str | None = None
        findings = list(output.findings)
        verified = False
        if independent_verifier is None:
            findings.append("INDEPENDENT_VERIFICATION_NOT_RUN")
        else:
            verifier_id, verifier_decision, verifier_findings = independent_verifier(output)
            findings.extend(verifier_findings)
            if verifier_id == executor.executor_id:
                findings.append("SELF_VERIFICATION_FORBIDDEN")
            verified = verifier_decision == "VERIFIED" and verifier_id != executor.executor_id
        status = output.status if verified else "BLOCKED" if output.status == "PASS" else output.status
        decision = "READY_FOR_EXTERNAL_GATE" if status == "PASS" and verified else "NOT_CERTIFIED"
        created = utc_now()
        seed = {"identity": identity.scope(), "type": campaign_type.value, "target": target.target_digest, "executor": executor.executor_id, "verifier": verifier_id, "evidence": [item.artifact.digest for item in evidence], "status": status}
        result = QualificationResult("qual_" + digest_of(seed).split(":", 1)[1], identity, campaign_type, target, status, executor.executor_id, verifier_id, authorization_ref, tuple(evidence), dict(output.metrics), tuple(findings), created, decision)
        self.store.put(result)
        return result


def default_production_qualification_plan(target_digest: str, environment_digest: str) -> Mapping[CampaignType, QualificationTarget]:
    if environment_digest == "sha256:" + "0" * 64:
        raise ContractViolation("qualification environment digest cannot be a placeholder")
    requirements: dict[CampaignType, Mapping[str, Any]] = {
        CampaignType.POSTGRES_TEMPORAL: {"postgres_failover": True, "temporal_replay": True, "object_store_outage": True, "worker_death": True},
        CampaignType.PRODUCTION_SANDBOX: {"isolation": ["L3", "L4"], "escape_suite": True, "tenant_bleed": True, "secret_revocation": True},
        CampaignType.PROVIDER_CONFORMANCE: {"minimum_adapters": 3, "identical_golden_tasks": True, "checkpoint_cancel_usage": True},
        CampaignType.BROWSER_DEVICE: {"engines": ["chromium", "firefox", "webkit"], "devices": True, "video": True, "accessibility": True},
        CampaignType.GOLDEN_REPO: {"repos_over_500k": 3, "repos_over_1m": 1, "independent_holdout": True},
        CampaignType.LOAD: {"active_idle_scaling": True, "event_fanout": True, "backpressure": True, "soak": True},
        CampaignType.CHAOS: {"failure_injections": 15, "deterministic_recovery": True},
        CampaignType.SECURITY_REVIEW: {"independent_reviewer": True, "red_team": True, "threat_model": True, "critical_findings": 0},
    }
    return {kind: QualificationTarget(kind.value, target_digest, environment_digest, value) for kind, value in requirements.items()}
