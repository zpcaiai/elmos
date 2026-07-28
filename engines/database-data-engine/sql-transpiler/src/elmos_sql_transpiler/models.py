from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

EvidenceState = Literal["PASSED", "FAILED", "NOT_RUN"]
CertificationState = Literal["NOT_CERTIFIED"]
TranspilationState = Literal["SYNTAX_READY", "BLOCKED"]


@dataclass(frozen=True)
class DialectProfile:
    id: str
    label: str
    engine: str
    engine_version: str
    edition: str
    dialect: str
    driver: str
    charset: str
    collation: str
    timezone: str
    compatibility_mode: str
    support_state: str
    runtime_evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "engine": self.engine,
            "engineVersion": self.engine_version,
            "edition": self.edition,
            "dialect": self.dialect,
            "driver": self.driver,
            "charset": self.charset,
            "collation": self.collation,
            "timezone": self.timezone,
            "compatibilityMode": self.compatibility_mode,
            "supportState": self.support_state,
            "runtimeEvidence": self.runtime_evidence,
        }


@dataclass(frozen=True)
class DirectedRoute:
    id: str
    source_profile: str
    target_profile: str
    state: str
    syntax_evidence: EvidenceState = "NOT_RUN"
    source_execution: EvidenceState = "NOT_RUN"
    target_execution: EvidenceState = "NOT_RUN"
    result_equivalence: EvidenceState = "NOT_RUN"
    certification: CertificationState = "NOT_CERTIFIED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sourceProfile": self.source_profile,
            "targetProfile": self.target_profile,
            "state": self.state,
            "syntaxEvidence": self.syntax_evidence,
            "sourceExecution": self.source_execution,
            "targetExecution": self.target_execution,
            "resultEquivalence": self.result_equivalence,
            "certification": self.certification,
        }


@dataclass(frozen=True)
class ParameterContract:
    name: str
    logical_type: str
    nullable: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TranspileRequest:
    query_id: str
    source_profile: str
    target_profile: str
    sql: str
    parameters: tuple[ParameterContract, ...] = ()


@dataclass(frozen=True)
class StatementIr:
    index: int
    kind: str
    source_ast: dict[str, Any] | list[Any]
    target_ast: dict[str, Any] | list[Any]
    obligations: tuple[str, ...]
    parameter_nodes_before: tuple[str, ...]
    parameter_nodes_after: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "kind": self.kind,
            "sourceAst": self.source_ast,
            "targetAst": self.target_ast,
            "obligations": list(self.obligations),
            "parameterNodesBefore": list(self.parameter_nodes_before),
            "parameterNodesAfter": list(self.parameter_nodes_after),
        }


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Literal["ERROR", "WARNING", "INFO"]
    statement_index: int | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "statementIndex": self.statement_index,
            "message": self.message,
        }


@dataclass(frozen=True)
class TranspileResult:
    schema_version: str
    query_id: str
    source_profile: DialectProfile
    target_profile: DialectProfile
    route: DirectedRoute
    state: TranspilationState
    source_digest: str
    target_digest: str | None
    target_sql: str | None
    statements: tuple[StatementIr, ...]
    diagnostics: tuple[Diagnostic, ...]
    syntax_parse: EvidenceState
    target_emit: EvidenceState
    target_reparse: EvidenceState
    parameter_contract: EvidenceState
    source_execution: EvidenceState = "NOT_RUN"
    target_execution: EvidenceState = "NOT_RUN"
    result_equivalence: EvidenceState = "NOT_RUN"
    error_equivalence: EvidenceState = "NOT_RUN"
    performance: EvidenceState = "NOT_RUN"
    security: EvidenceState = "NOT_RUN"
    certification: CertificationState = "NOT_CERTIFIED"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self, *, include_sql: bool = True) -> dict[str, Any]:
        result = {
            "schemaVersion": self.schema_version,
            "queryId": self.query_id,
            "sourceProfile": self.source_profile.to_dict(),
            "targetProfile": self.target_profile.to_dict(),
            "route": self.route.to_dict(),
            "state": self.state,
            "sourceDigest": self.source_digest,
            "targetDigest": self.target_digest,
            "statements": [item.to_dict() for item in self.statements],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "verification": {
                "syntaxParse": self.syntax_parse,
                "targetEmit": self.target_emit,
                "targetReparse": self.target_reparse,
                "parameterContract": self.parameter_contract,
                "sourceExecution": self.source_execution,
                "targetExecution": self.target_execution,
                "resultEquivalence": self.result_equivalence,
                "errorEquivalence": self.error_equivalence,
                "performance": self.performance,
                "security": self.security,
                "certification": self.certification,
            },
            "metadata": self.metadata,
        }
        if include_sql:
            result["targetSql"] = self.target_sql
        return result
