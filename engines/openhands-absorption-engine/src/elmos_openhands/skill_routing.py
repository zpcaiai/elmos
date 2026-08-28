"""Semantic/historical Skill routing and metered progressive disclosure."""

from __future__ import annotations

import math
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .context import estimate_tokens
from .errors import BudgetExceeded, ContractViolation, TenantIsolationError
from .models import canonical_json, digest_of
from .skills import ProgressiveSkillRouter, SkillMetadata


@dataclass(frozen=True, slots=True)
class SkillConstraints:
    languages: frozenset[str] = frozenset()
    runtimes: frozenset[str] = frozenset()
    task_types: frozenset[str] = frozenset()
    incompatible_skills: frozenset[str] = frozenset()
    max_risk: str = "R3"

    def __post_init__(self) -> None:
        if self.max_risk not in {f"R{value}" for value in range(7)}:
            raise ContractViolation("Skill risk constraint is invalid")


@dataclass(frozen=True, slots=True)
class IndexedSkill:
    metadata: SkillMetadata
    constraints: SkillConstraints = SkillConstraints()
    embedding: tuple[float, ...] = ()
    token_costs: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.embedding and (len(self.embedding) < 2 or not all(math.isfinite(value) for value in self.embedding)):
            raise ContractViolation("Skill embedding is invalid")


@dataclass(frozen=True, slots=True)
class SkillRoutingContext:
    tenant_id: str
    query: str
    permissions: frozenset[str] = frozenset()
    languages: frozenset[str] = frozenset()
    runtimes: frozenset[str] = frozenset()
    task_type: str | None = None
    active_skills: frozenset[str] = frozenset()
    max_risk: str = "R3"
    task_risk: str = "R0"

    def __post_init__(self) -> None:
        if self.max_risk not in {f"R{value}" for value in range(7)} or self.task_risk not in {f"R{value}" for value in range(7)}:
            raise ContractViolation("Skill routing risk context is invalid")


@dataclass(frozen=True, slots=True)
class RankedSkill:
    name: str
    version: str
    score: float
    semantic_score: float
    lexical_score: float
    historical_score: float
    warnings: tuple[str, ...]
    disclosure_stage: str = "L0_catalog"
    load_allowed: bool = True


class SkillRoutingStore:
    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(database), check_same_thread=False, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """CREATE TABLE IF NOT EXISTS skill_outcomes(tenant_id TEXT NOT NULL,skill_name TEXT NOT NULL,skill_version TEXT NOT NULL,outcome TEXT NOT NULL,score REAL NOT NULL,context_digest TEXT NOT NULL,created_at TEXT NOT NULL);
               CREATE TABLE IF NOT EXISTS skill_disclosures(tenant_id TEXT NOT NULL,skill_name TEXT NOT NULL,skill_version TEXT NOT NULL,stage TEXT NOT NULL,content_digest TEXT NOT NULL,tokens INTEGER NOT NULL,request_id TEXT NOT NULL,PRIMARY KEY(tenant_id,request_id,skill_name,stage));
               CREATE TABLE IF NOT EXISTS skill_token_usage(tenant_id TEXT NOT NULL,window_key TEXT NOT NULL,tokens INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(tenant_id,window_key));"""
        )
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def record_outcome(self, tenant_id: str, skill: SkillMetadata, outcome: str, score: float, context_digest: str) -> None:
        if outcome not in {"success", "failure", "blocked"} or not 0 <= score <= 1:
            raise ContractViolation("Skill outcome is invalid")
        from .models import utc_now

        with self._lock:
            self._connection.execute("INSERT INTO skill_outcomes VALUES(?,?,?,?,?,?,?)", (tenant_id, skill.name, skill.version, outcome, score, context_digest, utc_now()))

    def historical_score(self, tenant_id: str, skill: SkillMetadata) -> float:
        with self._lock:
            rows = self._connection.execute("SELECT outcome,score FROM skill_outcomes WHERE tenant_id=? AND skill_name=? AND skill_version=?", (tenant_id, skill.name, skill.version)).fetchall()
        if not rows:
            return 0.5
        weighted = [float(row["score"]) if row["outcome"] == "success" else 1.0 - float(row["score"]) for row in rows]
        return sum(weighted) / len(weighted)

    def account_disclosure(self, tenant_id: str, skill: SkillMetadata, stage: str, content: Mapping[str, Any], *, request_id: str, window_key: str, token_limit: int) -> int:
        tokens = estimate_tokens(canonical_json(dict(content)))
        digest = digest_of(dict(content))
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                self._connection.execute("INSERT OR IGNORE INTO skill_token_usage VALUES(?,?,0)", (tenant_id, window_key))
                used = int(self._connection.execute("SELECT tokens FROM skill_token_usage WHERE tenant_id=? AND window_key=?", (tenant_id, window_key)).fetchone()[0])
                existing = self._connection.execute("SELECT content_digest,tokens FROM skill_disclosures WHERE tenant_id=? AND request_id=? AND skill_name=? AND stage=?", (tenant_id, request_id, skill.name, stage)).fetchone()
                if existing is not None:
                    if existing["content_digest"] != digest:
                        raise ContractViolation("Skill disclosure content changed within one request")
                    self._connection.execute("COMMIT")
                    return int(existing["tokens"])
                if stage in {"L2_instructions", "L3_examples"}:
                    previous_stage = "L1_contract" if stage == "L2_instructions" else "L2_instructions"
                    previous = self._connection.execute("SELECT 1 FROM skill_disclosures WHERE tenant_id=? AND request_id=? AND skill_name=? AND stage=?", (tenant_id, request_id, skill.name, previous_stage)).fetchone()
                    if previous is None:
                        raise ContractViolation("Skill disclosure stages must be requested progressively")
                if used + tokens > token_limit:
                    raise BudgetExceeded("Skill disclosure token budget exceeded")
                self._connection.execute("INSERT INTO skill_disclosures VALUES(?,?,?,?,?,?,?)", (tenant_id, skill.name, skill.version, stage, digest, tokens, request_id))
                self._connection.execute("UPDATE skill_token_usage SET tokens=tokens+? WHERE tenant_id=? AND window_key=?", (tokens, tenant_id, window_key))
                self._connection.execute("COMMIT")
                return tokens
            except Exception:
                self._connection.execute("ROLLBACK")
                raise


class SemanticSkillRouter:
    def __init__(self, skills: Iterable[IndexedSkill], store: SkillRoutingStore, *, embed: Callable[[str], tuple[float, ...]]) -> None:
        self.skills = {skill.metadata.name: skill for skill in skills}
        self.store, self.embed = store, embed
        self.disclosure = ProgressiveSkillRouter(skill.metadata for skill in self.skills.values())

    def route(self, context: SkillRoutingContext, *, top_k: int = 5) -> tuple[RankedSkill, ...]:
        if not context.tenant_id or not context.query.strip() or top_k < 1:
            raise ContractViolation("Skill route request is invalid")
        query_embedding = self.embed(context.query)
        query_tokens = {token.lower() for token in context.query.split() if token}
        rows: list[RankedSkill] = []
        for item in self.skills.values():
            skill, constraints = item.metadata, item.constraints
            if skill.tenant_allowlist and context.tenant_id not in skill.tenant_allowlist:
                continue
            if not skill.permissions.issubset(context.permissions):
                continue
            if constraints.languages and not constraints.languages.intersection(context.languages):
                continue
            if constraints.runtimes and not constraints.runtimes.intersection(context.runtimes):
                continue
            if constraints.task_types and context.task_type not in constraints.task_types:
                continue
            if int(context.task_risk[1:]) > int(constraints.max_risk[1:]) or int(context.task_risk[1:]) > int(context.max_risk[1:]):
                continue
            warnings: list[str] = []
            conflicts = constraints.incompatible_skills & context.active_skills
            if conflicts:
                warnings.append("INCOMPATIBLE_ACTIVE_SKILLS:" + ",".join(sorted(conflicts)))
            lexical = len(query_tokens & {value.lower() for value in skill.keywords}) / max(1, len(query_tokens))
            semantic = _cosine(query_embedding, item.embedding) if item.embedding else 0.0
            historical = self.store.historical_score(context.tenant_id, skill)
            score = lexical * 0.35 + semantic * 0.45 + historical * 0.2
            rows.append(RankedSkill(skill.name, skill.version, score, semantic, lexical, historical, tuple(warnings), load_allowed=not conflicts))
        rows.sort(key=lambda row: (not row.load_allowed, -row.score, row.name))
        return tuple(rows[:top_k])

    def disclose(self, context: SkillRoutingContext, skill_name: str, stage: str, *, request_id: str, window_key: str, token_limit: int) -> Mapping[str, Any]:
        item = self.skills.get(skill_name)
        if item is None:
            raise KeyError(skill_name)
        if item.metadata.tenant_allowlist and context.tenant_id not in item.metadata.tenant_allowlist:
            raise TenantIsolationError("Skill is private to another tenant")
        if not item.metadata.permissions.issubset(context.permissions):
            raise ContractViolation("Skill permissions do not satisfy route request")
        conflicts = item.constraints.incompatible_skills & context.active_skills
        if conflicts:
            raise ContractViolation("Skill disclosure is blocked by active conflicts: " + ",".join(sorted(conflicts)))
        content = self.disclosure.disclose(context.tenant_id, skill_name, stage)
        tokens = self.store.account_disclosure(context.tenant_id, item.metadata, stage, content, request_id=request_id, window_key=window_key, token_limit=token_limit)
        return {**content, "tokens": tokens, "content_digest": digest_of(content)}


@dataclass(frozen=True, slots=True)
class SkillRoutingBenchmarkResult:
    top_k_recall: float
    unsafe_route_rate: float
    conflict_warning_recall: float
    status: str
    digest: str


class SkillRoutingBenchmark:
    def evaluate(self, cases: Iterable[tuple[tuple[str, ...], tuple[RankedSkill, ...], tuple[str, ...]]]) -> SkillRoutingBenchmarkResult:
        values = tuple(cases)
        if not values:
            raise ContractViolation("Skill routing benchmark cannot be empty")
        recall = 0.0
        unsafe = 0
        conflict_expected = 0
        conflict_found = 0
        for expected, actual, expected_conflicts in values:
            names = {item.name for item in actual}
            recall += len(names & set(expected)) / max(1, len(expected))
            unsafe += sum(any(warning.startswith("UNSAFE_ROUTE") for warning in item.warnings) for item in actual)
            conflict_expected += len(expected_conflicts)
            conflict_found += sum(any(conflict in warning for item in actual for warning in item.warnings) for conflict in expected_conflicts)
        top_k = recall / len(values)
        unsafe_rate = unsafe / max(1, sum(len(actual) for _, actual, _ in values))
        warning_recall = conflict_found / max(1, conflict_expected)
        status = "PASS" if top_k >= 0.9 and unsafe_rate == 0 and (conflict_expected == 0 or warning_recall == 1.0) else "FAIL"
        body = {"top_k_recall": top_k, "unsafe_route_rate": unsafe_rate, "conflict_warning_recall": warning_recall, "status": status}
        return SkillRoutingBenchmarkResult(top_k, unsafe_rate, warning_recall, status, digest_of(body))


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        raise ContractViolation("Skill/query embedding dimensions do not match")
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(-1.0, min(1.0, numerator / (left_norm * right_norm)))
