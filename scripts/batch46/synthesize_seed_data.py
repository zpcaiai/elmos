#!/usr/bin/env python3
"""Synthesize the minimal, disposable seed data for a one-click smoke run.

Data-source classes (docs/batch46/MINIMAL_DATA_POLICY.md):

  synthetic-from-contract  default; derived only from DDL/OpenAPI/env contracts
  desensitized-sample      opt-in; requires --sample-authorization and passes a
                           refusal-by-default sensitive-value scan
  corpus-trim              reuse of an existing development corpus slice

Production data is never a permitted source. Every emitted value is marked
`SMOKE-`/`smoke-` so an operator can recognise it on sight, and every artifact
is recorded in `smoke/seed-manifest.json` with its source class and digest.

Usage:
    python3 scripts/batch46/synthesize_seed_data.py <project-root> --write
    python3 scripts/batch46/synthesize_seed_data.py <project-root> --write \
        --sample fixtures/desensitized.json --sample-authorization DPA-2024-11
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from smoke_common import (
    DATA_CLASSIFICATION,
    DATA_SOURCES,
    SCHEMA_PREFIX,
    SEED_KEY_BASE,
    canonical_digest,
    deterministic_value,
    file_digest,
    read_json,
    read_text,
    smoke_dir,
    smoke_secret,
    utc_now,
    write_json,
)

SENSITIVE_VALUE_PATTERNS = {
    "email-like": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}"),
    "credit-card-like": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "national-id-like": re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{15}[\dxX]\b"),
    "bearer-token-like": re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{16,}"),
    "private-key-like": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
SENSITIVE_ALLOWLIST = re.compile(r"(?i)(smoke\.invalid|example\.com|SMOKE-|smoke-local-only-)")


def scan_sensitive(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for label, pattern in SENSITIVE_VALUE_PATTERNS.items():
        for match in pattern.finditer(text):
            snippet = match.group(0)
            if SENSITIVE_ALLOWLIST.search(snippet):
                continue
            findings.append({"pattern": label, "sample": snippet[:8] + "…"})
    return findings


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _column_value(seed: str, table: str, column: dict[str, Any], row_index: int) -> Any:
    kind = column.get("logical_type", "string")
    name = column["name"].lower()
    if column.get("primary_key") and kind == "int":
        # Reserved high range: a smoke row can never collide with an application row.
        offset = deterministic_value(f"{seed}|{table}|pk", "int", row_index)
        return SEED_KEY_BASE + int(offset) + row_index
    if "email" in name:
        kind = "email"
    elif name.endswith("phone") or name == "phone":
        kind = "phone"
    elif name.endswith("url"):
        kind = "url"
    return deterministic_value(f"{seed}|{table}|{column['name']}", kind, row_index)


def build_sql_seed(requirements: dict[str, Any], seed: str) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        "-- ELMOS Batch 46 smoke seed data.",
        "-- Class: ephemeral-disposable. Source: synthetic-from-contract.",
        "-- Never load this file into a shared or production database.",
        f"-- Primary keys are explicit and allocated from the reserved range >= {SEED_KEY_BASE}.",
        "-- Explicit keys do not advance identity sequences; that is acceptable for a",
        "-- throwaway smoke database and unacceptable anywhere else.",
        "",
    ]
    rows_meta: list[dict[str, Any]] = []
    datasets = sorted(requirements.get("datasets", []), key=lambda d: d.get("load_order", 999))
    referenced_tables = {
        fk["table"].split(".")[-1].lower()
        for dataset in datasets for fk in dataset.get("foreign_keys", [])
    }
    emitted: dict[str, dict[str, Any]] = {}
    for dataset in datasets:
        if dataset.get("kind") != "table":
            continue
        table = dataset["table"]
        needs_explicit_key = table.split(".")[-1].lower() in referenced_tables
        columns = [
            c for c in dataset["columns"]
            if not c.get("auto_generated") or (needs_explicit_key and c.get("primary_key"))
        ]
        min_rows = max(1, int(dataset.get("min_rows", 1)))
        for row_index in range(min_rows):
            values: dict[str, Any] = {}
            for column in columns:
                if column.get("nullable") and not column.get("primary_key") and not column.get("references"):
                    if not column.get("unique"):
                        continue  # minimal means: omit what the schema does not demand
                ref = column.get("references")
                if ref:
                    parent_key = ref["table"].split(".")[-1].lower()
                    parent = emitted.get(parent_key)
                    if parent and ref["column"] in parent:
                        values[column["name"]] = parent[ref["column"]]
                        continue
                values[column["name"]] = _column_value(seed, table, column, row_index)
            if not values:
                continue
            column_list = ", ".join(values)
            value_list = ", ".join(_sql_literal(v) for v in values.values())
            lines.append(f"INSERT INTO {table} ({column_list}) VALUES ({value_list});")
            if row_index == 0:
                emitted[table.split(".")[-1].lower()] = values
            rows_meta.append({"table": table, "row_index": row_index, "columns": list(values)})
    lines.append("")
    return "\n".join(lines), rows_meta


def build_env(requirements: dict[str, Any], seed: str, runtime: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    lines = [
        "# ELMOS Batch 46 smoke environment. Disposable, local-only, never committed to a deployed config.",
    ]
    meta: list[dict[str, Any]] = []
    for entry in requirements.get("environment", []):
        name = entry["name"]
        if entry.get("secret"):
            value = smoke_secret(seed, name)
            strategy = "throwaway-secret"
        elif name in runtime:
            value = runtime[name]
            strategy = "derived-from-runtime"
        elif entry.get("template_value") and not _is_placeholder(entry["template_value"]):
            value = entry["template_value"]
            strategy = "contract-default"
        else:
            value = deterministic_value(f"{seed}|env", "string", 0)
            strategy = "synthetic-from-contract"
        lines.append(f"{name}={value}")
        meta.append({"name": name, "strategy": strategy, "secret": bool(entry.get("secret"))})
    for name, value in runtime.items():
        if not any(m["name"] == name for m in meta):
            lines.append(f"{name}={value}")
            meta.append({"name": name, "strategy": "derived-from-runtime", "secret": False})
    lines.append("")
    return "\n".join(lines), meta


def _is_placeholder(value: str) -> bool:
    low = (value or "").strip().lower()
    return low in ("", "changeme", "todo", "xxx", "<set-me>", "replace_me") or low.startswith("<")


COMPOSE_DSN = {
    "postgres": "postgresql://smoke:smoke-local-only@127.0.0.1:5432/smoke",
    "mysql": "mysql://root:smoke-local-only@127.0.0.1:3306/smoke",
    "mongodb": "mongodb://127.0.0.1:27017/smoke",
    "redis": "redis://127.0.0.1:6379/0",
}


def build_runtime_overrides(profile: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    """Per-entry environment overrides for connection-shaped variables.

    A connection string copied from `.env.example` points at whatever the author
    had locally. The smoke entries stand up their own ephemeral topology, so the
    value has to follow the entry, not the template.
    """
    engines = [d["engine"] for d in profile.get("datastores", [])]
    primary_sql = next((e for e in engines if e in ("postgres", "mysql", "sqlserver", "oracle", "sqlite")), None)
    overrides: dict[str, dict[str, str]] = {"compose": {}, "zero-dep": {}, "script": {}}
    unresolved: list[dict[str, str]] = []
    for entry in requirements.get("environment", []):
        if entry.get("smoke_value_strategy") != "derived-from-runtime":
            continue
        name = entry["name"]
        low = name.lower()
        engine = (
            "redis" if "redis" in low else
            "mongodb" if "mongo" in low else
            primary_sql
        )
        if engine in COMPOSE_DSN:
            overrides["compose"][name] = COMPOSE_DSN[engine]
        if engine in ("postgres", "mysql", "sqlite", "sqlserver") and ("url" in low or "dsn" in low):
            overrides["zero-dep"][name] = "sqlite:///${SMOKE_SQLITE_PATH}"
        if engine is None:
            unresolved.append({
                "name": name,
                "reason": "connection-shaped variable with no detected datastore; the contract default is kept",
            })
    return {
        "schema": f"{SCHEMA_PREFIX}.runtime-overrides/1",
        "note": (
            "Applied by smoke/tools/run_smoke.py for the selected entry. ${SMOKE_SQLITE_PATH} "
            "is expanded at run time. The 'script' entry intentionally overrides nothing: it "
            "runs against whatever the operator already has."
        ),
        "by_entry": overrides,
        "unresolved": unresolved,
    }


def build_api_fixtures(requirements: dict[str, Any], profile: dict[str, Any], seed: str) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    for endpoint in requirements.get("candidate_smoke_endpoints", []):
        routes.append({
            "method": endpoint["method"],
            "path": endpoint["path"],
            "status": 200,
            "body": {
                "id": deterministic_value(f"{seed}|api|{endpoint['path']}", "uuid"),
                "name": deterministic_value(f"{seed}|api|{endpoint['path']}", "string"),
                "smokeFixture": True,
            },
        })
    if not routes:
        routes.append({
            "method": "GET",
            "path": "/",
            "status": 200,
            "body": {"smokeFixture": True, "note": "default stub route; no API contract was detected"},
        })
    return {
        "schema": f"{SCHEMA_PREFIX}.api-stub-fixtures/1",
        "classification": DATA_CLASSIFICATION,
        "routes": routes,
    }


def _apply_sample(sample_path: Path, authorization: str | None, allow_findings: bool) -> dict[str, Any]:
    text = read_text(sample_path)
    findings = scan_sensitive(text)
    if not authorization:
        raise SystemExit(
            "error: --sample requires --sample-authorization <reference to the approval that permits reuse>"
        )
    if findings and not allow_findings:
        detail = ", ".join(sorted({f['pattern'] for f in findings}))
        raise SystemExit(
            f"error: sample still contains sensitive-looking values ({detail}); "
            "desensitize it or re-run with --accept-scan-findings and record the approval"
        )
    return {
        "path": str(sample_path),
        "digest": file_digest(sample_path),
        "authorization": authorization,
        "scan_findings": findings,
        "accepted_with_findings": bool(findings and allow_findings),
    }


def synthesize(root: Path, args: argparse.Namespace) -> dict[str, Any]:
    root = Path(root).resolve()
    profile = read_json(smoke_dir(root) / "profile.json")
    requirements = read_json(smoke_dir(root) / "minimal-data-requirements.json")
    seed = args.seed or requirements.get("requirements_digest", "elmos-batch46")

    seed_dir = smoke_dir(root) / "seed"
    seed_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []

    runtime_env: dict[str, str] = {"SMOKE_MODE": "1", "ELMOS_SMOKE_DATA": DATA_CLASSIFICATION}

    sql_text, rows_meta = build_sql_seed(requirements, seed)
    if rows_meta:
        sql_path = seed_dir / "seed.sql"
        if args.write:
            sql_path.write_text(sql_text, encoding="utf-8")
        artifacts.append({
            "id": "seed.sql",
            "path": "smoke/seed/seed.sql",
            "data_source": "synthetic-from-contract",
            "classification": DATA_CLASSIFICATION,
            "rows": len(rows_meta),
            "tables": sorted({r["table"] for r in rows_meta}),
            "digest": file_digest(sql_path) if args.write and sql_path.is_file() else None,
        })

    fixtures = build_api_fixtures(requirements, profile, seed)
    fixtures_path = seed_dir / "api-fixtures.json"
    if args.write:
        write_json(fixtures_path, fixtures)
    artifacts.append({
        "id": "api-fixtures.json",
        "path": "smoke/seed/api-fixtures.json",
        "data_source": "synthetic-from-contract",
        "classification": DATA_CLASSIFICATION,
        "routes": len(fixtures["routes"]),
        "digest": file_digest(fixtures_path) if args.write and fixtures_path.is_file() else None,
    })

    overrides = build_runtime_overrides(profile, requirements)
    overrides_path = seed_dir / "runtime-overrides.json"
    if args.write:
        write_json(overrides_path, overrides)
    artifacts.append({
        "id": "runtime-overrides.json",
        "path": "smoke/seed/runtime-overrides.json",
        "data_source": "synthetic-from-contract",
        "classification": DATA_CLASSIFICATION,
        "entries": sorted(overrides["by_entry"]),
        "digest": file_digest(overrides_path) if args.write and overrides_path.is_file() else None,
    })

    env_text, env_meta = build_env(requirements, seed, runtime_env)
    env_path = seed_dir / "env.smoke"
    if args.write:
        env_path.write_text(env_text, encoding="utf-8")
    artifacts.append({
        "id": "env.smoke",
        "path": "smoke/seed/env.smoke",
        "data_source": "synthetic-from-contract",
        "classification": DATA_CLASSIFICATION,
        "variables": len(env_meta),
        "secrets": sum(1 for m in env_meta if m["secret"]),
        "digest": file_digest(env_path) if args.write and env_path.is_file() else None,
    })

    provenance: list[dict[str, Any]] = [{
        "data_source": "synthetic-from-contract",
        "derived_from": sorted({d["source_file"] for d in requirements.get("datasets", []) if d.get("source_file")})
        + profile.get("env_contract_files", []) + profile.get("api_contract_files", []),
    }]
    if args.sample:
        provenance.append({
            "data_source": "desensitized-sample",
            **_apply_sample(Path(args.sample), args.sample_authorization, args.accept_scan_findings),
        })
    if args.corpus:
        corpus = Path(args.corpus)
        if not corpus.is_dir():
            raise SystemExit(f"error: corpus directory not found: {corpus}")
        files = sorted(p for p in corpus.rglob("*") if p.is_file())[: args.corpus_max_files]
        provenance.append({
            "data_source": "corpus-trim",
            "corpus_root": str(corpus),
            "files": [str(p.relative_to(corpus)) for p in files],
            "independence_note": (
                "corpus-trim may reuse development corpora only; holdout and representative "
                "workload corpora must stay untouched"
            ),
        })

    manifest: dict[str, Any] = {
        "schema": f"{SCHEMA_PREFIX}.seed-manifest/1",
        "generated_at": utc_now(),
        "seed": seed,
        "deterministic": True,
        "classification": DATA_CLASSIFICATION,
        "allowed_data_sources": list(DATA_SOURCES),
        "production_data_used": False,
        "provenance": provenance,
        "artifacts": artifacts,
        "teardown": {
            "drop_on_expiry": True,
            "targets": ["ephemeral database volume", "generated seed files", "stub upstream state"],
        },
        "unsupported": requirements.get("unsupported", []),
        "unknown": requirements.get("unknown", []),
    }
    manifest["seed_manifest_digest"] = canonical_digest(
        {k: v for k, v in manifest.items() if k not in ("generated_at", "seed_manifest_digest")}
    )
    if args.write:
        write_json(smoke_dir(root) / "seed-manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthesize minimal disposable smoke seed data")
    parser.add_argument("project_root")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--seed", help="deterministic seed; defaults to the requirements digest")
    parser.add_argument("--sample", help="desensitized sample file to register as an additional source")
    parser.add_argument("--sample-authorization", help="approval reference permitting sample reuse")
    parser.add_argument("--accept-scan-findings", action="store_true",
                        help="record and accept sensitive-scan findings on the sample (requires authorization)")
    parser.add_argument("--corpus", help="development corpus directory to trim from")
    parser.add_argument("--corpus-max-files", type=int, default=20)
    args = parser.parse_args()
    manifest = synthesize(Path(args.project_root), args)
    if args.write:
        print(f"wrote smoke/seed-manifest.json ({len(manifest['artifacts'])} artifacts)")
    else:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
