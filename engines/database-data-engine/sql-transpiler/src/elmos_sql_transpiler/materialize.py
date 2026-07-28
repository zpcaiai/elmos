from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import TranspileResult
from .runner import runner_capabilities


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_output_directory(output: Path) -> Path:
    resolved = output.resolve()
    if resolved == Path("/") or resolved == Path.home().resolve():
        raise ValueError("broad output directories are prohibited")
    if resolved.exists() and any(resolved.iterdir()):
        raise FileExistsError("output directory must be absent or empty")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _runner_config(profile_id: str, permissions: list[str]) -> dict[str, Any]:
    capabilities = runner_capabilities()
    matches = [
        item
        for item in capabilities["ready"] + capabilities["blocked"]
        if item["profileId"] == profile_id
    ]
    if len(matches) != 1:
        raise RuntimeError(f"missing exact Runner configuration for {profile_id}")
    exact = dict(matches[0])
    state = str(exact.pop("state"))
    return {
        "profile": profile_id,
        "status": state,
        "runtimeEvidence": "NOT_RUN",
        "exactRuntime": exact,
        "permissions": permissions,
    }


def materialize(result: TranspileResult, output: Path) -> dict[str, Any]:
    target = _safe_output_directory(output)
    if result.state != "SYNTAX_READY" or result.target_sql is None:
        raise ValueError("blocked transpilation cannot be materialized as target SQL")

    (target / "target.sql").write_text(result.target_sql, encoding="utf-8")
    _write_json(
        target / "canonical-ir" / "query-ir.json",
        {
            "schemaVersion": result.schema_version,
            "queryId": result.query_id,
            "sourceDigest": result.source_digest,
            "targetDigest": result.target_digest,
            "statements": [statement.to_dict() for statement in result.statements],
        },
    )
    _write_json(target / "route.json", result.route.to_dict())
    _write_json(
        target / "source-reference.json",
        {
            "queryId": result.query_id,
            "sourceDigest": result.source_digest,
            "rawSourceSqlPersisted": False,
            "sourceAstPersisted": True,
            "sourceProfile": result.source_profile.to_dict(),
        },
    )
    _write_json(
        target / "target-profile.json",
        result.target_profile.to_dict(),
    )
    _write_json(
        target / "verification.json",
        result.to_dict(include_sql=False)["verification"],
    )
    _write_json(
        target / "runner-config.json",
        {
            "schemaVersion": "1.0",
            "sourceRunner": _runner_config(
                result.source_profile.id,
                ["READ_QUERY", "READ_METADATA"],
            ),
            "targetRunner": _runner_config(
                result.target_profile.id,
                ["DISPOSABLE_SCHEMA_DDL", "DISPOSABLE_FIXTURE_DML"],
            ),
            "productionWrites": "PROHIBITED_WITHOUT_SEPARATE_APPROVAL",
            "credentialMode": "SHORT_LIVED_LEASE_REQUIRED",
        },
    )
    _write_json(target / "transpilation-report.json", result.to_dict(include_sql=False))
    files = sorted(str(path.relative_to(target)) for path in target.rglob("*") if path.is_file())
    return {
        "output": str(target),
        "files": files,
        "fileCount": len(files),
        "syntaxState": result.state,
        "sourceExecution": result.source_execution,
        "targetExecution": result.target_execution,
        "resultEquivalence": result.result_equivalence,
        "certification": result.certification,
    }
