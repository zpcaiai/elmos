"""Skill 04 — compiling natural-language intent into checkable constraints.

Goals arrive as prose.  Plans need predicates.  This module does that
translation deterministically and, crucially, **records what it could not
translate** rather than inventing a confident reading.

Three outputs matter downstream:

``CompiledIntent``
    Goal atoms: an operation, its targets, and the confidence with which the
    targets were resolved against the semantic index.
``AcceptancePredicates``
    "Do not change behaviour" decomposed into source / binary / wire / data /
    behaviour / operational predicates that a gate can actually evaluate.
``AssumptionRegister``
    Every inference, with its source and confidence.  A low-confidence
    assumption about an irreversible operation blocks; it does not proceed with
    a note in the log.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .contracts import RiskClass, sha256_payload
from .index import SemanticIndex
from .plan import Assumption
from .request import RefactorRequest


class Operation(StrEnum):
    """The refactoring operations the compiler can recognise."""

    RENAME_SYMBOL = "rename-symbol"
    MOVE_MODULE = "move-module"
    EXTRACT_MODULE = "extract-module"
    MERGE_MODULE = "merge-module"
    SPLIT_SERVICE = "split-service"
    CHANGE_SIGNATURE = "change-api-signature"
    REMOVE_DEAD_CODE = "remove-dead-code"
    BREAK_CYCLE = "break-dependency-cycle"
    UPGRADE_DEPENDENCY = "upgrade-dependency"
    UPGRADE_FRAMEWORK = "upgrade-framework"
    SYNC_TO_ASYNC = "sync-to-async"
    ERROR_MODEL_MIGRATION = "error-model-migration"
    SCHEMA_EXPAND_CONTRACT = "schema-expand-contract"
    CONTRACT_EVOLUTION = "contract-evolution"
    PERFORMANCE = "performance-optimisation"
    SECURITY_HARDENING = "security-hardening"
    UI_MIGRATION = "ui-migration"
    UNCLASSIFIED = "unclassified"

    @property
    def irreversible_risk(self) -> bool:
        return self in {
            Operation.SCHEMA_EXPAND_CONTRACT,
            Operation.SPLIT_SERVICE,
            Operation.SECURITY_HARDENING,
            Operation.CONTRACT_EVOLUTION,
        }


#: Keyword tables.  Both English and Chinese are recognised because the Skills
#: package, its runbooks and its users are bilingual; a goal written in Chinese
#: must not silently fall through to ``unclassified``.
_OPERATION_KEYWORDS: Mapping[Operation, tuple[str, ...]] = {
    Operation.RENAME_SYMBOL: ("rename", "renaming", "重命名", "改名"),
    Operation.MOVE_MODULE: ("move", "relocate", "移动", "迁移模块", "包重命名", "package rename"),
    Operation.EXTRACT_MODULE: ("extract", "pull out", "抽取", "拆出", "提取"),
    Operation.MERGE_MODULE: ("merge", "consolidate", "合并", "收敛"),
    Operation.SPLIT_SERVICE: ("split", "decompose", "monolith", "拆分", "单体", "服务边界"),
    Operation.CHANGE_SIGNATURE: ("signature", "parameter", "argument", "签名", "参数"),
    Operation.REMOVE_DEAD_CODE: ("dead code", "unused", "remove unused", "废弃代码", "删除无用"),
    Operation.BREAK_CYCLE: ("cycle", "circular", "cyclic", "循环依赖", "环"),
    Operation.UPGRADE_DEPENDENCY: ("upgrade dependency", "bump", "dependency upgrade", "依赖升级"),
    Operation.UPGRADE_FRAMEWORK: ("upgrade", "migrate to", "spring boot", "框架升级", "版本升级"),
    Operation.SYNC_TO_ASYNC: ("async", "asynchronous", "coroutine", "异步", "同步转异步"),
    Operation.ERROR_MODEL_MIGRATION: ("error handling", "exception", "error type", "错误处理", "异常模型"),
    Operation.SCHEMA_EXPAND_CONTRACT: ("schema", "column", "table", "migration", "数据库", "字段", "表结构"),
    Operation.CONTRACT_EVOLUTION: ("api", "endpoint", "proto", "graphql", "contract", "契约", "接口"),
    Operation.PERFORMANCE: ("performance", "latency", "throughput", "性能", "延迟", "吞吐"),
    Operation.SECURITY_HARDENING: ("security", "auth", "permission", "安全", "鉴权", "权限"),
    Operation.UI_MIGRATION: ("component", "hooks", "react", "vue", "flutter", "小程序", "组件"),
}

#: Identifier-shaped tokens in a goal: dotted names, ``Class.method``,
#: quoted names and path-like fragments.
_TARGET_TOKEN = re.compile(
    r"""
    `(?P<quoted>[^`]+)`
  | '(?P<single>[^']+)'
  | "(?P<double>[^"]+)"
  | (?P<dotted>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)
  | (?P<camel>[A-Z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*)
  | (?P<snake>[a-z][a-z0-9]*(?:_[a-z0-9]+)+)
    """,
    re.VERBOSE,
)

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "with", "from", "into", "that", "this", "must", "should",
        "not", "all", "any", "use", "using", "make", "keep", "our", "its",
    }
)


@dataclass(frozen=True, slots=True)
class GoalAtom:
    """One goal, classified."""

    index: int
    text: str
    operation: Operation
    targets: tuple[str, ...]
    resolved_entities: tuple[str, ...]
    confidence: Decimal

    def to_payload(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "operation": self.operation.value,
            "targets": list(self.targets),
            "resolvedEntities": list(self.resolved_entities),
            "confidence": str(self.confidence),
        }


class PredicateDomain(StrEnum):
    SOURCE = "source"
    BINARY = "binary"
    WIRE = "wire"
    DATA = "data"
    BEHAVIOR = "behavior"
    OPERATIONAL = "operational"


@dataclass(frozen=True, slots=True)
class AcceptancePredicate:
    id: str
    domain: PredicateDomain
    expression: str
    origin: str
    blocking: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain": self.domain.value,
            "expression": self.expression,
            "origin": self.origin,
            "blocking": self.blocking,
        }


@dataclass(frozen=True, slots=True)
class ScopePolicy:
    allowed_paths: tuple[str, ...]
    forbidden_paths: tuple[str, ...]
    protected_symbols: tuple[str, ...] = ()
    maximum_changed_files: int | None = None
    maximum_changed_lines: int | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "allowedPaths": list(self.allowed_paths),
            "forbiddenPaths": list(self.forbidden_paths),
            "protectedSymbols": list(self.protected_symbols),
            "maximumChangedFiles": self.maximum_changed_files,
            "maximumChangedLines": self.maximum_changed_lines,
        }


@dataclass(frozen=True, slots=True)
class ConstraintConflict:
    minimal_set: tuple[str, ...]
    explanation: str

    def to_payload(self) -> dict[str, Any]:
        return {"minimalSet": list(self.minimal_set), "explanation": self.explanation}


@dataclass(frozen=True, slots=True)
class CompiledIntent:
    goals: tuple[GoalAtom, ...]
    non_goals: tuple[str, ...]
    predicates: tuple[AcceptancePredicate, ...]
    assumptions: tuple[Assumption, ...]
    scope: ScopePolicy
    conflicts: tuple[ConstraintConflict, ...] = ()
    risk_floor: RiskClass = RiskClass.R0

    @property
    def operations(self) -> tuple[Operation, ...]:
        return tuple(dict.fromkeys(goal.operation for goal in self.goals))

    @property
    def unclassified_goals(self) -> tuple[GoalAtom, ...]:
        return tuple(goal for goal in self.goals if goal.operation is Operation.UNCLASSIFIED)

    @property
    def blocking_assumptions(self) -> tuple[Assumption, ...]:
        return tuple(item for item in self.assumptions if item.blocks_execution)

    @property
    def executable(self) -> bool:
        return not self.conflicts and not self.blocking_assumptions

    def to_payload(self) -> dict[str, Any]:
        return {
            "goals": [goal.to_payload() for goal in self.goals],
            "nonGoals": list(self.non_goals),
            "operations": [item.value for item in self.operations],
            "acceptancePredicates": [item.to_payload() for item in self.predicates],
            "assumptions": [item.to_payload() for item in self.assumptions],
            "scopePolicy": self.scope.to_payload(),
            "conflicts": [item.to_payload() for item in self.conflicts],
            "riskFloor": self.risk_floor.value,
            "executable": self.executable,
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def _classify(text: str) -> tuple[Operation, Decimal]:
    lowered = text.lower()
    scores: dict[Operation, int] = {}
    for operation, keywords in _OPERATION_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in lowered)
        if hits:
            scores[operation] = hits
    if not scores:
        return Operation.UNCLASSIFIED, Decimal("0")
    best = max(scores.items(), key=lambda item: (item[1], item[0].value))
    #: Confidence reflects how *distinctive* the match was: one operation with
    #: several keyword hits is a strong signal; several operations tied is not.
    contenders = sum(1 for value in scores.values() if value == best[1])
    confidence = Decimal(best[1]) / Decimal(best[1] + contenders - 1 + 1)
    return best[0], confidence.quantize(Decimal("0.01"))


def _targets(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _TARGET_TOKEN.finditer(text):
        value = next((item for item in match.groupdict().values() if item), None)
        if value is None:
            continue
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in _STOPWORDS or len(cleaned) < 3:
            continue
        found.append(cleaned)
    return tuple(dict.fromkeys(found))


def _resolve(targets: Sequence[str], index: SemanticIndex | None) -> tuple[tuple[str, ...], Decimal]:
    if index is None or not targets:
        return (), Decimal("0")
    resolved: list[str] = []
    hits = 0
    for target in targets:
        matches = index.by_qualified_name(target) or index.by_name(target.rsplit(".", 1)[-1])
        if matches:
            hits += 1
            resolved.extend(entity.id for entity in matches[:8])
    ratio = Decimal(hits) / Decimal(len(targets))
    return tuple(dict.fromkeys(resolved)), ratio.quantize(Decimal("0.01"))


_COMPATIBILITY_PREDICATES: Mapping[str, tuple[tuple[PredicateDomain, str], ...]] = {
    "strict": (
        (PredicateDomain.SOURCE, "gates.parse and gates.typecheck and gates.build"),
        (PredicateDomain.BEHAVIOR, "tests.changed_target_pass and tests.regressions == 0"),
        (PredicateDomain.WIRE, "api.wire_breaks == 0"),
        (PredicateDomain.BINARY, "api.binary_breaks == 0"),
        (PredicateDomain.DATA, "schema.destructive_changes == 0"),
        (PredicateDomain.OPERATIONAL, "rollout.rollback_verified"),
    ),
    "equivalent-for-covered-workloads": (
        (PredicateDomain.BEHAVIOR, "tests.changed_target_pass and coverage.changed_symbols >= 0.8"),
        (PredicateDomain.WIRE, "api.wire_breaks == 0"),
    ),
    "approved-change": ((PredicateDomain.BEHAVIOR, "approvals.behavior_change_signed"),),
}

_API_PREDICATES: Mapping[str, tuple[tuple[PredicateDomain, str], ...]] = {
    "strict": ((PredicateDomain.SOURCE, "api.source_breaks == 0 and api.additive_only"),),
    "backward-compatible": ((PredicateDomain.SOURCE, "api.source_breaks == 0"),),
    "versioned-break": ((PredicateDomain.WIRE, "api.new_version_published"),),
    "approved-break": ((PredicateDomain.SOURCE, "approvals.api_break_signed"),),
}

_DATABASE_PREDICATES: Mapping[str, tuple[tuple[PredicateDomain, str], ...]] = {
    "none": (),
    "expand-contract": (
        (PredicateDomain.DATA, "schema.phases_ordered and schema.backfill_resumable"),
        (PredicateDomain.DATA, "schema.old_path_usage == 0"),
    ),
    "maintenance-window": ((PredicateDomain.OPERATIONAL, "approvals.maintenance_window_signed"),),
    "approved-destructive": ((PredicateDomain.DATA, "approvals.destructive_migration_signed"),),
}


def compile_intent(
    request: RefactorRequest,
    index: SemanticIndex | None = None,
    *,
    unknown_risk_weight: Decimal = Decimal("0"),
) -> CompiledIntent:
    """Compile a request's prose into machine-checkable constraints."""

    goals: list[GoalAtom] = []
    assumptions: list[Assumption] = []

    for position, text in enumerate(request.intent.goals):
        operation, keyword_confidence = _classify(text)
        targets = _targets(text)
        entities, resolution = _resolve(targets, index)
        confidence = (keyword_confidence + resolution) / Decimal(2)
        goals.append(
            GoalAtom(
                index=position,
                text=text,
                operation=operation,
                targets=targets,
                resolved_entities=entities,
                confidence=confidence.quantize(Decimal("0.01")),
            )
        )
        if operation is Operation.UNCLASSIFIED:
            assumptions.append(
                Assumption(
                    id=f"goal-{position}-unclassified",
                    statement=f"goal {position} could not be mapped to a known operation: {text!r}",
                    status="requires-approval",
                    confidence=Decimal("0"),
                    source="intent-compiler",
                )
            )
        elif not targets:
            assumptions.append(
                Assumption(
                    id=f"goal-{position}-no-target",
                    statement=(
                        f"goal {position} names no concrete symbol, module or path; "
                        "the change set will be inferred from impact analysis alone"
                    ),
                    status="unverified",
                    confidence=Decimal("0.3"),
                    source="intent-compiler",
                )
            )
        elif index is not None and not entities:
            assumptions.append(
                Assumption(
                    id=f"goal-{position}-unresolved-target",
                    statement=(
                        f"goal {position} names {', '.join(targets)}, none of which resolve "
                        "in the semantic index for this revision"
                    ),
                    status="requires-approval" if operation.irreversible_risk else "unverified",
                    confidence=Decimal("0.1"),
                    source="intent-compiler",
                )
            )

    predicates = _build_predicates(request)
    scope = _build_scope(request, index)
    conflicts = _detect_conflicts(request, goals)

    if unknown_risk_weight > Decimal("0.2"):
        assumptions.append(
            Assumption(
                id="index-unknown-risk",
                statement=(
                    f"the semantic index reports unknown-risk weight {unknown_risk_weight}; "
                    "impact closure may be incomplete"
                ),
                status="requires-approval",
                confidence=Decimal("1") - unknown_risk_weight,
                source="semantic-index",
            )
        )

    for position, criterion in enumerate(request.intent.acceptance_criteria):
        predicates = (
            *predicates,
            AcceptancePredicate(
                id=f"acceptance-{position}",
                domain=PredicateDomain.BEHAVIOR,
                expression=f"approvals.acceptance_{position}_confirmed",
                origin=f"user acceptance criterion: {criterion}",
                blocking=True,
            ),
        )

    return CompiledIntent(
        goals=tuple(goals),
        non_goals=request.intent.non_goals,
        predicates=predicates,
        assumptions=tuple(assumptions),
        scope=scope,
        conflicts=conflicts,
        risk_floor=request.risk_floor,
    )


def _build_predicates(request: RefactorRequest) -> tuple[AcceptancePredicate, ...]:
    constraints = request.constraints
    collected: list[AcceptancePredicate] = []
    sources = (
        ("behaviorCompatibility", constraints.behavior_compatibility, _COMPATIBILITY_PREDICATES),
        ("publicApiCompatibility", constraints.public_api_compatibility, _API_PREDICATES),
        ("databaseStrategy", constraints.database_strategy, _DATABASE_PREDICATES),
    )
    for origin, value, table in sources:
        for position, (domain, expression) in enumerate(table.get(value, ())):
            collected.append(
                AcceptancePredicate(
                    id=f"{origin}-{position}",
                    domain=domain,
                    expression=expression,
                    origin=f"{origin}={value}",
                )
            )
    if constraints.binary_compatibility == "strict":
        collected.append(
            AcceptancePredicate(
                id="binaryCompatibility-strict",
                domain=PredicateDomain.BINARY,
                expression="api.binary_breaks == 0",
                origin="binaryCompatibility=strict",
            )
        )
    for name, threshold in sorted(constraints.performance_guardrails.items()):
        collected.append(
            AcceptancePredicate(
                id=f"performance-{name}",
                domain=PredicateDomain.OPERATIONAL,
                expression=f"performance.{name} <= {threshold}",
                origin=f"performanceGuardrails.{name}",
            )
        )
    for position, test in enumerate(constraints.required_tests):
        collected.append(
            AcceptancePredicate(
                id=f"required-test-{position}",
                domain=PredicateDomain.BEHAVIOR,
                expression=f"tests.passed contains '{test}'",
                origin=f"requiredTests[{position}]",
            )
        )
    return tuple(collected)


def _build_scope(request: RefactorRequest, index: SemanticIndex | None) -> ScopePolicy:
    constraints = request.constraints
    forbidden = list(constraints.forbidden_paths)
    protected: list[str] = []

    #: Non-goals become protection rather than prose: a non-goal that names a
    #: path forbids it, and one that names a symbol protects that symbol.
    for statement in request.intent.non_goals:
        for token in _targets(statement):
            if "/" in token or token.endswith((".py", ".ts", ".java", ".go", ".sql")):
                forbidden.append(token)
            else:
                protected.append(token)
        if index is not None:
            for token in _targets(statement):
                protected.extend(entity.qualified_name for entity in index.by_name(token) if entity.qualified_name)

    return ScopePolicy(
        allowed_paths=constraints.allowed_paths or ("**",),
        forbidden_paths=tuple(dict.fromkeys(forbidden)),
        protected_symbols=tuple(dict.fromkeys(protected)),
        maximum_changed_files=constraints.maximum_changed_files,
        maximum_changed_lines=constraints.maximum_changed_lines,
    )


def _detect_conflicts(request: RefactorRequest, goals: Sequence[GoalAtom]) -> tuple[ConstraintConflict, ...]:
    """Find minimal contradictory constraint sets.

    Reporting the *minimal* set matters: telling an operator that "something in
    your 14 constraints conflicts" is not actionable, and picking a resolution
    for them silently is worse.
    """

    conflicts: list[ConstraintConflict] = []
    constraints = request.constraints
    operations = {goal.operation for goal in goals}

    if constraints.behavior_compatibility == "strict" and Operation.PERFORMANCE in operations:
        conflicts.append(
            ConstraintConflict(
                ("behaviorCompatibility=strict", "goal:performance-optimisation"),
                "strict behaviour compatibility forbids the observable timing changes an optimisation goal expects; "
                "choose equivalent-for-covered-workloads or state the permitted deltas as guardrails",
            )
        )
    if constraints.public_api_compatibility == "strict" and Operation.CHANGE_SIGNATURE in operations:
        conflicts.append(
            ConstraintConflict(
                ("publicApiCompatibility=strict", "goal:change-api-signature"),
                "a signature change cannot be strictly source-compatible; use backward-compatible with an "
                "overload/adapter, or versioned-break",
            )
        )
    if constraints.database_strategy == "none" and Operation.SCHEMA_EXPAND_CONTRACT in operations:
        conflicts.append(
            ConstraintConflict(
                ("databaseStrategy=none", "goal:schema-expand-contract"),
                "a schema goal requires an explicit database strategy",
            )
        )
    if constraints.maximum_changed_files is not None and constraints.maximum_changed_files < len(goals):
        conflicts.append(
            ConstraintConflict(
                ("maximumChangedFiles", "intent.goals"),
                f"maximumChangedFiles={constraints.maximum_changed_files} cannot cover {len(goals)} goal(s)",
            )
        )
    if Operation.SPLIT_SERVICE in operations and constraints.database_strategy == "none":
        conflicts.append(
            ConstraintConflict(
                ("goal:split-service", "databaseStrategy=none"),
                "splitting a service without a database strategy leaves the two halves sharing one schema, "
                "which is the coupling the split is meant to remove",
            )
        )
    return tuple(conflicts)


__all__ = [
    "AcceptancePredicate",
    "CompiledIntent",
    "ConstraintConflict",
    "GoalAtom",
    "Operation",
    "PredicateDomain",
    "ScopePolicy",
    "compile_intent",
]
