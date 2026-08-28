from __future__ import annotations

import base64
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from .artifact_store import ContentAddressedArtifactStore
from .canonical import canonical_json, digest_bytes, digest_value
from .contracts import AssuranceLevel, ProofStatus, Scope, TrustedIdentity, utc_now
from .execution import (
    ExecutionAuthorizationError,
    ExecutionContractError,
    ExecutionPermitSigner,
    ExecutionState,
    NativeExecutionReceipt,
    NativeExecutionRequest,
    ResourceLimits,
)
from .store import StateStore


_FORBIDDEN_SQL = re.compile(
    r"\b(?:attach|detach)\b|\bload_extension\s*\(|\bwritable_schema\b|\bvacuum\s+.*\binto\b",
    re.IGNORECASE | re.DOTALL,
)
_READ_QUERY = re.compile(r"^\s*(?:select|with)\b", re.IGNORECASE)


def _split_sql(script: str) -> list[str]:
    if not isinstance(script, str):
        raise ExecutionContractError("database fixture SQL must be text")
    if len(script.encode("utf-8")) > 4 * 1024 * 1024:
        raise ExecutionContractError("database fixture SQL exceeds the local bound")
    if _FORBIDDEN_SQL.search(script):
        raise ExecutionAuthorizationError("database fixture contains a forbidden operation")
    statements: list[str] = []
    pending = ""
    for character in script:
        pending += character
        if character == ";" and sqlite3.complete_statement(pending):
            if pending.strip(" \t\r\n;"):
                statements.append(pending)
            pending = ""
    if pending.strip():
        if not sqlite3.complete_statement(pending + ";"):
            raise ExecutionContractError("database fixture contains incomplete SQL")
        statements.append(pending)
    if len(statements) > 10_000:
        raise ExecutionContractError("database fixture exceeds the statement-count bound")
    return statements


def _cell(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "integer", "value": int(value)}
    if isinstance(value, int):
        return {"type": "integer", "value": value}
    if isinstance(value, float):
        return {"type": "real", "value": repr(value)}
    if isinstance(value, str):
        return {"type": "text", "value": value}
    if isinstance(value, bytes):
        return {
            "type": "blob",
            "base64": base64.b64encode(value).decode("ascii"),
            "sha256": digest_bytes(value),
        }
    raise ExecutionContractError(f"unsupported SQLite value type: {type(value).__name__}")


def _rows(values: list[tuple[Any, ...]], ordered: bool) -> list[list[dict[str, Any]]]:
    result = [[_cell(cell) for cell in row] for row in values]
    if not ordered:
        result.sort(key=canonical_json)
    return result


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


@dataclass(frozen=True, slots=True)
class DatabaseSideResult:
    schema: list[dict[str, Any]]
    query_rows: list[list[dict[str, Any]]]
    state: dict[str, list[list[dict[str, Any]]]]
    affected_rows: list[int]
    error: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "queryRows": self.query_rows,
            "state": self.state,
            "affectedRows": self.affected_rows,
            "error": self.error,
        }


class SQLiteDifferentialExecutor:
    """Disposable, deterministic source/target SQL differential harness."""

    _REQUIRED = {
        "source/schema.sql",
        "source/query.sql",
        "target/schema.sql",
        "target/query.sql",
    }
    _OPTIONAL = {
        "source/seed.sql",
        "source/action.sql",
        "target/seed.sql",
        "target/action.sql",
    }

    def __init__(
        self,
        *,
        store: StateStore,
        artifact_store: ContentAddressedArtifactStore | None,
        permit_signer: ExecutionPermitSigner | None,
        limits: ResourceLimits,
    ) -> None:
        self.store = store
        self.artifact_store = artifact_store
        self.permit_signer = permit_signer
        self.limits = limits

    def execute(
        self,
        *,
        scope: Scope,
        identity: TrustedIdentity,
        skill_id: str,
        subject_id: str,
        payload: Mapping[str, Any],
    ) -> NativeExecutionReceipt | None:
        raw = payload.get("productionExecution")
        if not isinstance(raw, dict) or raw.get("adapterId") != "sqlite-differential":
            return None
        request = NativeExecutionRequest.from_payload(
            raw,
            scope=scope,
            skill_id=skill_id,
            subject_id=subject_id,
            limits=self.limits,
        )
        if request.query_semantics != "DIFFERENTIAL_EXECUTION":
            raise ExecutionContractError(
                "sqlite-differential requires DIFFERENTIAL_EXECUTION semantics"
            )
        paths = {item.path for item in request.files}
        if not self._REQUIRED.issubset(paths) or not paths.issubset(
            self._REQUIRED | self._OPTIONAL
        ):
            raise ExecutionContractError(
                "sqlite-differential file set must contain exact source/target schema and query fixtures"
            )
        options = dict(request.options)
        allowed_options = {"ordered", "compare", "maxRows", "progressSteps"}
        if set(options) - allowed_options:
            raise ExecutionContractError("sqlite-differential received unknown options")
        ordered = options.get("ordered", False)
        if not isinstance(ordered, bool):
            raise ExecutionContractError("sqlite-differential ordered must be boolean")
        compare = options.get(
            "compare", ["schema", "queryRows", "state", "affectedRows", "error"]
        )
        if (
            not isinstance(compare, list)
            or not compare
            or any(
                value not in {"schema", "queryRows", "state", "affectedRows", "error"}
                for value in compare
            )
        ):
            raise ExecutionContractError("sqlite-differential compare profile is invalid")
        max_rows = options.get("maxRows", 100_000)
        progress_steps = options.get("progressSteps", 5_000_000)
        for name, value, maximum in (
            ("maxRows", max_rows, 1_000_000),
            ("progressSteps", progress_steps, 100_000_000),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= maximum:
                raise ExecutionContractError(f"sqlite-differential {name} is outside policy")
        if self.permit_signer is None:
            raise ExecutionAuthorizationError("database execution permit authority is not configured")
        self.permit_signer.verify(
            request.permit,
            scope=scope,
            identity=identity,
            skill_id=skill_id,
            subject_id=subject_id,
            adapter_id=request.adapter_id,
            execution_digest=request.binding_digest,
        )
        self.store.consume_execution_permit(
            scope,
            request.permit.permit_id,
            request.permit.nonce,
            request.binding_digest,
            request.permit.expires_at_epoch,
        )
        fixtures = {item.path: item.data.decode("utf-8") for item in request.files}
        started = utc_now()
        start_ns = __import__("time").monotonic_ns()
        source = self._run_side(fixtures, "source", ordered, max_rows, progress_steps)
        target = self._run_side(fixtures, "target", ordered, max_rows, progress_steps)
        duration_ms = (__import__("time").monotonic_ns() - start_ns) // 1_000_000
        source_doc, target_doc = source.to_dict(), target.to_dict()
        mismatches = [name for name in compare if source_doc[name] != target_doc[name]]
        counterexample = None
        if mismatches:
            counterexample = {
                "mismatchedDimensions": mismatches,
                "sourceDigest": digest_value({name: source_doc[name] for name in mismatches}),
                "targetDigest": digest_value({name: target_doc[name] for name in mismatches}),
            }
            proof_status = ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
            assurance = AssuranceLevel.NONE
        else:
            proof_status = ProofStatus.BOUNDED_NO_COUNTEREXAMPLE
            assurance = AssuranceLevel.A1_BOUNDED
        input_manifest = [
            {"path": item.path, "sha256": digest_bytes(item.data), "sizeBytes": len(item.data)}
            for item in request.files
        ]
        evidence = {
            "format": "elmos-sqlite-differential-evidence/v1",
            "sqliteVersion": sqlite3.sqlite_version,
            "bindingDigest": request.binding_digest,
            "ordered": ordered,
            "compare": compare,
            "source": source_doc,
            "target": target_doc,
            "mismatches": mismatches,
            "counterexample": counterexample,
            "bound": {"maxRows": max_rows, "progressSteps": progress_steps},
        }
        artifacts: list[dict[str, Any]] = []
        if self.artifact_store is not None:
            artifacts.append(
                self.artifact_store.put(
                    scope.tenant_id,
                    canonical_json(evidence) + b"\n",
                    media_type="application/vnd.elmos.sqlite-differential+json",
                    retention_class="AUDIT",
                )
            )
        execution_id = "exec-" + request.binding_digest.removeprefix("sha256:")[:32]
        receipt = NativeExecutionReceipt(
            execution_id=execution_id,
            adapter_id=request.adapter_id,
            binding_digest=request.binding_digest,
            toolchain_digest=digest_value(
                {
                    "engine": "python-sqlite3",
                    "sqliteVersion": sqlite3.sqlite_version,
                    "sqliteVersionInfo": list(sqlite3.sqlite_version_info),
                }
            ),
            state=ExecutionState.COMPLETED,
            proof_status=proof_status,
            assurance_level=assurance,
            started_at=started,
            duration_ms=int(duration_ms),
            exit_code=0,
            containment="IN_MEMORY_DISPOSABLE_SQLITE_AUTHORIZER_PROGRESS_BOUND",
            command_digest=digest_value(
                {"adapter": "sqlite-differential", "compare": compare, "ordered": ordered}
            ),
            input_manifest_digest=digest_value(input_manifest),
            version_output_digest=digest_bytes(sqlite3.sqlite_version.encode("utf-8")),
            artifact_refs=tuple(artifacts),
            diagnostics=(
                "disposable SQLite differential execution is local engineering evidence; exact source/target provider evidence remains NOT_RUN",
            ),
            counterexample=counterexample,
        )
        self.store.put_execution_receipt(
            scope, execution_id, request.binding_digest, receipt.to_dict()
        )
        return receipt

    @staticmethod
    def _authorizer(
        action: int, arg1: str | None, arg2: str | None, database: str | None, trigger: str | None
    ) -> int:
        del database, trigger
        denied = {
            getattr(sqlite3, "SQLITE_ATTACH", -1),
            getattr(sqlite3, "SQLITE_DETACH", -2),
        }
        if action in denied:
            return sqlite3.SQLITE_DENY
        if action == getattr(sqlite3, "SQLITE_FUNCTION", -3) and str(arg2 or arg1).lower() == "load_extension":
            return sqlite3.SQLITE_DENY
        if action == getattr(sqlite3, "SQLITE_PRAGMA", -4):
            allowed = {"foreign_keys", "table_info", "index_list", "index_info", "index_xinfo"}
            if str(arg1).lower() not in allowed:
                return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    def _run_side(
        self,
        fixtures: Mapping[str, str],
        side: str,
        ordered: bool,
        max_rows: int,
        progress_steps: int,
    ) -> DatabaseSideResult:
        connection = sqlite3.connect(":memory:", isolation_level=None)
        connection.enable_load_extension(False)
        connection.set_authorizer(self._authorizer)
        progress = 0

        def progress_handler() -> int:
            nonlocal progress
            progress += 1000
            return 1 if progress > progress_steps else 0

        connection.set_progress_handler(progress_handler, 1000)
        affected: list[int] = []
        error: dict[str, Any] | None = None
        query_rows: list[list[dict[str, Any]]] = []
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            for phase in ("schema", "seed", "action"):
                script = fixtures.get(f"{side}/{phase}.sql", "")
                for statement in _split_sql(script):
                    cursor = connection.execute(statement)
                    if phase == "action":
                        affected.append(max(cursor.rowcount, 0))
            query = fixtures[f"{side}/query.sql"]
            statements = _split_sql(query)
            if len(statements) != 1 or not _READ_QUERY.match(statements[0]):
                raise ExecutionAuthorizationError("comparison query must be one SELECT/WITH statement")
            cursor = connection.execute(statements[0])
            values = cursor.fetchmany(max_rows + 1)
            if len(values) > max_rows:
                raise ExecutionContractError("database comparison exceeded maxRows")
            query_rows = _rows(values, ordered)
        except sqlite3.Error as exc:
            error = {
                "class": type(exc).__name__,
                "sqliteErrorCode": getattr(exc, "sqlite_errorcode", None),
                "sqliteErrorName": getattr(exc, "sqlite_errorname", None),
            }
        schema = self._schema_snapshot(connection)
        state = self._state_snapshot(connection, max_rows)
        connection.close()
        return DatabaseSideResult(schema, query_rows, state, affected, error)

    @staticmethod
    def _schema_snapshot(connection: sqlite3.Connection) -> list[dict[str, Any]]:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result: list[dict[str, Any]] = []
        for table in tables:
            columns = [
                {
                    "position": row[0],
                    "name": row[1],
                    "type": str(row[2]).upper(),
                    "notNull": bool(row[3]),
                    "default": row[4],
                    "primaryKeyPosition": row[5],
                }
                for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
            ]
            indexes = [
                {"name": row[1], "unique": bool(row[2]), "origin": row[3], "partial": bool(row[4])}
                for row in connection.execute(f"PRAGMA index_list({_quote(table)})")
            ]
            result.append({"table": table, "columns": columns, "indexes": indexes})
        return result

    @staticmethod
    def _state_snapshot(
        connection: sqlite3.Connection, max_rows: int
    ) -> dict[str, list[list[dict[str, Any]]]]:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        result: dict[str, list[list[dict[str, Any]]]] = {}
        remaining = max_rows
        for table in tables:
            values = connection.execute(f"SELECT * FROM {_quote(table)}").fetchmany(remaining + 1)
            if len(values) > remaining:
                raise ExecutionContractError("database state snapshot exceeded maxRows")
            result[table] = _rows(values, False)
            remaining -= len(values)
        return result


__all__ = ["DatabaseSideResult", "SQLiteDifferentialExecutor"]
