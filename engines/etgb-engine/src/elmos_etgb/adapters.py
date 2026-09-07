"""Repository-owned adapters for offline fixtures and explicit unavailable routes."""

from __future__ import annotations

import json
import re
import sqlite3
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

from .evidence import EvidenceStore
from .oracles import compare_json
from .security import ExecutionPolicy, SecurityBoundaryError, resolve_within, run_command_sequence


class AdapterUnavailable(RuntimeError):
    """The required external harness is not installed or attested."""


def _artifact(store: EvidenceStore | None, value: Any, *, role: str) -> dict[str, Any]:
    if store is not None:
        return store.put_json(value, role=role)
    return {"role": role, "inline": value}


def _process_artifacts(store: EvidenceStore | None, process: dict[str, Any], prefix: str) -> list[dict[str, Any]]:
    if store is None:
        return [{"role": f"{prefix}-process", "inline": process}]
    return [
        store.put_text(process.get("stdout", ""), media_type="text/plain", role=f"{prefix}-stdout"),
        store.put_text(process.get("stderr", ""), media_type="text/plain", role=f"{prefix}-stderr"),
        store.put_json(process, role=f"{prefix}-process"),
    ]


def _parse_json_output(text: str) -> Any:
    if not text.strip():
        raise ValueError("process produced empty stdout")
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        for line in reversed(text.splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise ValueError("stdout does not contain a JSON value")


def execute_local_process(case: dict[str, Any], root: Path, *, store: EvidenceStore | None = None) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
    spec = case["execution"]
    source_cwd = resolve_within(root, spec["cwd"])
    with tempfile.TemporaryDirectory(prefix="etgb-local-workspace-") as temporary:
        workspace = Path(temporary) / "workspace"
        shutil.copytree(source_cwd, workspace)
        policy = ExecutionPolicy(root=Path(temporary), timeout_seconds=int(spec["timeout_seconds"]), max_output_bytes=int(spec.get("max_output_bytes", 2 * 1024 * 1024)))
        process = run_command_sequence(str(spec["command"]), workspace, policy, env=spec.get("env"))
    passed = process["returncode"] == 0 and not process["timed_out"] and not process["output_truncated"]
    oracle = {"type": "process-success", "critical": True, "passed": passed, "returncode": process["returncode"], "timed_out": process["timed_out"], "output_truncated": process["output_truncated"]}
    evidence = {"process": process, "artifacts": _process_artifacts(store, process, "local")}
    return ("passed" if passed else "failed", [oracle], evidence, False)


def execute_differential_process(case: dict[str, Any], root: Path, *, store: EvidenceStore | None = None) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
    spec = case["execution"]
    timeout = int(spec["timeout_seconds"])
    source_cwd = resolve_within(root, spec["source_cwd"])
    target_cwd = resolve_within(root, spec["target_cwd"])
    with tempfile.TemporaryDirectory(prefix="etgb-differential-workspace-") as temporary:
        workspace = Path(temporary)
        source_workspace = workspace / "source"
        target_workspace = workspace / "target"
        shutil.copytree(source_cwd, source_workspace)
        shutil.copytree(target_cwd, target_workspace)
        source_policy = ExecutionPolicy(root=workspace, timeout_seconds=timeout, max_output_bytes=int(spec.get("max_output_bytes", 2 * 1024 * 1024)))
        target_policy = ExecutionPolicy(root=workspace, timeout_seconds=timeout, max_output_bytes=int(spec.get("max_output_bytes", 2 * 1024 * 1024)))
        source = run_command_sequence(str(spec["source_command"]), source_workspace, source_policy, env=spec.get("source_env"))
        target = run_command_sequence(str(spec["target_command"]), target_workspace, target_policy, env=spec.get("target_env"))
    build_pass = all(item["returncode"] == 0 and not item["timed_out"] and not item["output_truncated"] for item in (source, target))
    oracles: list[dict[str, Any]] = [{"type": "both-processes-success", "critical": True, "passed": build_pass, "source_returncode": source["returncode"], "target_returncode": target["returncode"]}]
    source_value: Any = None
    target_value: Any = None
    comparison: dict[str, Any]
    if build_pass:
        try:
            source_value = _parse_json_output(source["stdout"])
            target_value = _parse_json_output(target["stdout"])
            comparison = compare_json(source_value, target_value)
        except Exception as exc:
            comparison = {"type": "json-equivalence", "passed": False, "first_difference": {"path": "$", "reason": "output-parse-error", "message": str(exc)}}
    else:
        comparison = {"type": "json-equivalence", "passed": False, "first_difference": {"path": "$", "reason": "process-failed"}}
    comparison["critical"] = True
    oracles.append(comparison)
    passed = build_pass and comparison["passed"] is True
    evidence = {
        "source_process": source,
        "target_process": target,
        "normalized_source": source_value,
        "normalized_target": target_value,
        "first_difference": comparison.get("first_difference"),
        "artifacts": _process_artifacts(store, source, "source") + _process_artifacts(store, target, "target"),
    }
    return ("passed" if passed else "failed", oracles, evidence, build_pass and not comparison["passed"])


def execute_json_file_differential(case: dict[str, Any], root: Path, *, store: EvidenceStore | None = None) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
    spec = case["execution"]
    source_path = resolve_within(root, spec["source_path"])
    target_path = resolve_within(root, spec["target_path"])
    source = json.loads(source_path.read_text(encoding="utf-8"))
    target = json.loads(target_path.read_text(encoding="utf-8"))
    comparison = compare_json(source, target, ignore_paths=spec.get("ignore_paths", []), unordered_paths=spec.get("unordered_paths", []), absolute_tolerance=float(spec.get("absolute_tolerance", 0.0)), relative_tolerance=float(spec.get("relative_tolerance", 0.0)))
    comparison["type"] = "json-file-equivalence"
    comparison["critical"] = True
    evidence = {
        "source_path": str(source_path.relative_to(root)),
        "target_path": str(target_path.relative_to(root)),
        "source": source,
        "target": target,
        "artifacts": [_artifact(store, source, role="source-json"), _artifact(store, target, role="target-json"), _artifact(store, comparison, role="json-comparison")],
    }
    return ("passed" if comparison["passed"] else "failed", [comparison], evidence, not comparison["passed"])


_DANGEROUS_SQL = re.compile(r"(?is)\b(?:attach|detach|load_extension)\b|\bload_extension\s*\(")
_WRITE_SQL = re.compile(r"(?is)\b(?:insert|update|delete|replace|create|drop|alter|vacuum|reindex)\b|;")


def _authorizer(action: int, arg1: str | None, arg2: str | None, *_: str) -> int:
    denied = {getattr(sqlite3, "SQLITE_ATTACH", -1), getattr(sqlite3, "SQLITE_DETACH", -1), getattr(sqlite3, "SQLITE_LOAD_EXTENSION", -1)}
    if action in denied:
        return sqlite3.SQLITE_DENY
    if action == getattr(sqlite3, "SQLITE_FUNCTION", -1) and str(arg2 or arg1 or "").lower() == "load_extension":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _execute_script(connection: sqlite3.Connection, path: Path) -> None:
    content = path.read_text(encoding="utf-8")
    if len(content.encode("utf-8")) > 2 * 1024 * 1024 or _DANGEROUS_SQL.search(content):
        raise SecurityBoundaryError(f"unsafe SQLite script: {path}")
    connection.executescript(content)
    connection.commit()


def _rows(connection: sqlite3.Connection, query: str) -> list[list[Any]]:
    cursor = connection.execute(query)
    return [list(row) for row in cursor.fetchall()]


def _table_state(connection: sqlite3.Connection) -> dict[str, Any]:
    tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    state: dict[str, Any] = {}
    for table in tables:
        quoted = '"' + str(table).replace('"', '""') + '"'
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({quoted})")]
        if columns:
            order = ",".join('"' + str(column).replace('"', '""') + '"' for column in columns)
            rows = [list(row) for row in connection.execute(f"SELECT * FROM {quoted} ORDER BY {order}")]
        else:
            rows = []
        state[str(table)] = {"columns": columns, "rows": rows}
    return state


def _schema(connection: sqlite3.Connection) -> list[list[Any]]:
    return _rows(connection, "SELECT type,name,tbl_name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")


def execute_sqlite_differential(case: dict[str, Any], root: Path, *, store: EvidenceStore | None = None) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
    spec = case["execution"]
    seed_path = resolve_within(root, spec["seed_sql"])
    source_path = resolve_within(root, spec["source_sql"])
    target_path = resolve_within(root, spec["target_sql"])
    with tempfile.TemporaryDirectory(prefix="etgb-sql-") as temporary:
        source_connection = sqlite3.connect(Path(temporary) / "source.db")
        target_connection = sqlite3.connect(Path(temporary) / "target.db")
        try:
            for connection in (source_connection, target_connection):
                connection.execute("PRAGMA foreign_keys=ON")
                connection.set_authorizer(_authorizer)
                connection.enable_load_extension(False)
                _execute_script(connection, seed_path)
            _execute_script(source_connection, source_path)
            _execute_script(target_connection, target_path)
            queries = list(spec.get("assertion_queries", []))
            for query in queries:
                if not isinstance(query, str) or _WRITE_SQL.search(query):
                    raise SecurityBoundaryError("assertion query must be a single read-only statement")
            source_results = {query: _rows(source_connection, query) for query in queries}
            target_results = {query: _rows(target_connection, query) for query in queries}
            source_state = _table_state(source_connection)
            target_state = _table_state(target_connection)
            source_schema = _schema(source_connection)
            target_schema = _schema(target_connection)
            result_comparison = compare_json(source_results, target_results)
            state_comparison = compare_json(source_state, target_state)
            schema_comparison = compare_json(source_schema, target_schema)
            for comparison in (result_comparison, state_comparison, schema_comparison):
                comparison["critical"] = True
            passed = all(comparison["passed"] for comparison in (result_comparison, state_comparison, schema_comparison))
            oracles = [
                {**result_comparison, "type": "result-set-equivalence"},
                {**state_comparison, "type": "database-state-equivalence"},
                {**schema_comparison, "type": "schema-object-equivalence"},
            ]
            evidence_payload = {"source_results": source_results, "target_results": target_results, "source_state": source_state, "target_state": target_state, "source_schema": source_schema, "target_schema": target_schema}
            evidence = {**evidence_payload, "artifacts": [_artifact(store, evidence_payload, role="sqlite-differential")]}
            return ("passed" if passed else "failed", oracles, evidence, not passed)
        finally:
            source_connection.close()
            target_connection.close()


EXECUTORS: dict[str, Callable[..., tuple[str, list[dict[str, Any]], dict[str, Any], bool]]] = {
    "local-process": execute_local_process,
    "differential-process": execute_differential_process,
    "json-file-differential": execute_json_file_differential,
    "sqlite-differential": execute_sqlite_differential,
}


V11_EXTERNAL_ADAPTERS = frozenset({
    "external-transformation-harness",
    "external-repository-translation-harness",
    "external-project-generation-harness",
    "external-project-evolution-harness",
    "external-requirement-reasoning-harness",
    "external-dual-database-harness",
    "external-fault-injection-harness",
})


V20_EXTERNAL_ADAPTERS = frozenset({
    "external-agent-protocol-harness",
    "external-ai-runtime-harness",
    "external-ai-solution-factory-harness",
    "external-analytics-admin-harness",
    "external-api-sdk-harness",
    "external-artifact-render-harness",
    "external-billing-ledger-harness",
    "external-collaboration-integration-harness",
    "external-commercial-certification-harness",
    "external-control-plane-harness",
    "external-data-platform-harness",
    "external-deployment-chaos-harness",
    "external-identity-access-harness",
    "external-ingestion-harness",
    "external-multimodal-processing-harness",
    "external-notification-scheduler-harness",
    "external-online-ide-debug-harness",
    "external-payment-sandbox-harness",
    "external-product-journey-harness",
    "external-project-intelligence-harness",
    "external-rag-memory-harness",
    "external-security-compliance-harness",
    "external-standards-assurance-harness",
    "external-storage-search-cache-harness",
    "external-ui-accessibility-harness",
})


# The caller accepts only package-owned, exact adapter identities.  Keeping the
# v1.1 and v2.0 sets explicit prevents a package from gaining network authority
# by inventing an ``external-*`` name in repository content.
EXTERNAL_ADAPTERS = V11_EXTERNAL_ADAPTERS | V20_EXTERNAL_ADAPTERS
