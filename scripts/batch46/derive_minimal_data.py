#!/usr/bin/env python3
"""Derive the minimal data a generated project needs in order to start.

Reads `smoke/profile.json` plus the project's own contracts (env templates, SQL
DDL, OpenAPI) and writes `smoke/minimal-data-requirements.json`.

"Minimal" is defined narrowly: the smallest set of environment values, database
rows and stub upstreams without which the process cannot reach a ready state or
serve one functional request. Anything beyond that belongs in a real test
corpus, not in a smoke pack.

Usage:
    python3 scripts/batch46/derive_minimal_data.py <project-root> [--write]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from smoke_common import (
    SCHEMA_PREFIX,
    canonical_digest,
    is_secret_name,
    read_json,
    read_text,
    smoke_dir,
    utc_now,
    write_json,
)

CREATE_TABLE_RE = re.compile(
    r"create\s+table\s+(?:if\s+not\s+exists\s+)?([\"`\[\]\w\.]+)\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
TYPE_RE = re.compile(r"^\s*([\"`\[\]\w]+)\s+([\w]+)\s*(\([^)]*\))?(.*)$", re.IGNORECASE)
REFERENCES_RE = re.compile(r"references\s+([\"`\[\]\w\.]+)\s*\(\s*([\"`\w]+)\s*\)", re.IGNORECASE)
TABLE_CONSTRAINT_PREFIXES = (
    "primary key", "foreign key", "unique", "check", "constraint", "key ", "index ",
)

SQL_TYPE_MAP = {
    "int": "int", "integer": "int", "bigint": "int", "smallint": "int", "tinyint": "int",
    "serial": "int", "bigserial": "int", "int4": "int", "int8": "int",
    "decimal": "decimal", "numeric": "decimal", "money": "decimal", "float": "decimal",
    "double": "decimal", "real": "decimal", "float8": "decimal",
    "bool": "bool", "boolean": "bool", "bit": "bool",
    "uuid": "uuid", "uniqueidentifier": "uuid",
    "date": "date", "time": "time",
    "timestamp": "timestamp", "timestamptz": "timestamp", "datetime": "timestamp",
    "datetime2": "timestamp", "datetimeoffset": "timestamp",
    "json": "json", "jsonb": "json",
}


def _clean(identifier: str) -> str:
    return identifier.strip().strip('"').strip("`").strip("[").strip("]")


def parse_sql_schema(sql_text: str) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for match in CREATE_TABLE_RE.finditer(sql_text):
        raw_name = _clean(match.group(1))
        body = match.group(2)
        columns: list[dict[str, Any]] = []
        depth = 0
        buffer: list[str] = []
        parts: list[str] = []
        for char in body:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            if char == "," and depth == 0:
                parts.append("".join(buffer))
                buffer = []
            else:
                buffer.append(char)
        if buffer:
            parts.append("".join(buffer))
        table_pk: list[str] = []
        for part in parts:
            stripped = part.strip()
            low = stripped.lower()
            if not stripped:
                continue
            if low.startswith(TABLE_CONSTRAINT_PREFIXES):
                if low.startswith("primary key"):
                    inner = stripped[stripped.find("(") + 1: stripped.rfind(")")]
                    table_pk.extend(_clean(c) for c in inner.split(","))
                continue
            type_match = TYPE_RE.match(stripped)
            if not type_match:
                continue
            name = _clean(type_match.group(1))
            raw_type = type_match.group(2).lower()
            tail = (type_match.group(4) or "").lower()
            ref = REFERENCES_RE.search(stripped)
            columns.append({
                "name": name,
                "sql_type": raw_type,
                "logical_type": SQL_TYPE_MAP.get(raw_type, "string"),
                "nullable": "not null" not in tail and "primary key" not in tail,
                "primary_key": "primary key" in tail,
                "unique": "unique" in tail,
                "has_default": "default" in tail,
                "auto_generated": raw_type in ("serial", "bigserial") or "identity" in tail or "autoincrement" in tail,
                "references": (
                    {"table": _clean(ref.group(1)), "column": _clean(ref.group(2))} if ref else None
                ),
            })
        for column in columns:
            if column["name"] in table_pk:
                column["primary_key"] = True
                column["nullable"] = False
        tables.append({"table": raw_name, "columns": columns})
    return tables


def _topological_order(tables: list[dict[str, Any]]) -> list[str]:
    names = [t["table"] for t in tables]
    short = {n.split(".")[-1].lower(): n for n in names}
    edges: dict[str, set[str]] = {n: set() for n in names}
    for table in tables:
        for column in table["columns"]:
            ref = column.get("references")
            if not ref:
                continue
            target = short.get(ref["table"].split(".")[-1].lower())
            if target and target != table["table"]:
                edges[table["table"]].add(target)
    ordered: list[str] = []
    seen: set[str] = set()
    guard = 0
    while len(ordered) < len(names) and guard <= len(names) + 1:
        guard += 1
        for name in names:
            if name in seen:
                continue
            if edges[name] <= seen:
                ordered.append(name)
                seen.add(name)
    for name in names:
        if name not in seen:
            ordered.append(name)  # cycle: keep declaration order and flag downstream
    return ordered


def _env_from_files(root: Path, profile: dict[str, Any]) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for rel_path in profile.get("env_contract_files", []):
        path = root / rel_path
        text = read_text(path)
        if path.suffix == ".json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            for key, value in _flatten_json(data):
                entries.setdefault(key, {
                    "name": key,
                    "required": True,
                    "detected_in": rel_path,
                    "template_value": value,
                })
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", key):
                continue
            entries.setdefault(key, {
                "name": key,
                "required": True,
                "detected_in": rel_path,
                "template_value": value.strip(),
            })
    result = []
    for entry in entries.values():
        entry["secret"] = is_secret_name(entry["name"])
        entry["smoke_value_strategy"] = (
            "throwaway-secret" if entry["secret"]
            else "derived-from-runtime" if _looks_like_connection(entry["name"], entry.get("template_value", ""))
            else "synthetic-from-contract"
        )
        result.append(entry)
    return sorted(result, key=lambda e: e["name"])


def _looks_like_connection(name: str, value: str) -> bool:
    blob = f"{name} {value}".lower()
    return any(marker in blob for marker in ("url", "uri", "dsn", "host", "port", "connection"))


def _flatten_json(data: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            out.extend(_flatten_json(value, f"{prefix}{key}." if not prefix else f"{prefix}{key}."))
    elif prefix:
        out.append((prefix.rstrip("."), data))
    return out


def _openapi_endpoints(root: Path, profile: dict[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    for rel_path in profile.get("api_contract_files", []):
        if not rel_path.endswith(".json"):
            continue
        try:
            spec = read_json(root / rel_path)
        except (json.JSONDecodeError, OSError):
            continue
        for path, methods in (spec.get("paths") or {}).items():
            for method, operation in (methods or {}).items():
                if method.lower() not in ("get", "post"):
                    continue
                if "{" in path and method.lower() == "get":
                    continue
                endpoints.append({
                    "path": path,
                    "method": method.upper(),
                    "operation_id": (operation or {}).get("operationId"),
                    "source": rel_path,
                })
    return endpoints[:10]


def derive(root: Path, profile: dict[str, Any]) -> dict[str, Any]:
    root = Path(root).resolve()
    datasets: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = list(profile.get("unknown", []))

    schema_files: list[str] = []
    for store in profile.get("datastores", []):
        schema_files.extend(store.get("schema_files", []))
    schema_files = sorted(set(schema_files))

    tables: list[dict[str, Any]] = []
    for rel_path in schema_files:
        parsed = parse_sql_schema(read_text(root / rel_path))
        for table in parsed:
            table["source_file"] = rel_path
        tables.extend(parsed)

    order = _topological_order(tables)
    order_index = {name: i for i, name in enumerate(order)}
    for table in sorted(tables, key=lambda t: order_index.get(t["table"], 999)):
        required_columns = [c for c in table["columns"] if not c["nullable"] and not c["auto_generated"] and not c["has_default"]]
        datasets.append({
            "id": f"db.{table['table']}",
            "kind": "table",
            "table": table["table"],
            "source_file": table["source_file"],
            "load_order": order_index.get(table["table"], 999),
            "min_rows": 1,
            "columns": table["columns"],
            "required_columns": [c["name"] for c in required_columns],
            "foreign_keys": [
                {"column": c["name"], **c["references"]} for c in table["columns"] if c.get("references")
            ],
        })
        for column in table["columns"]:
            if column["logical_type"] == "string" and column["sql_type"] not in (
                "varchar", "nvarchar", "char", "nchar", "text", "ntext", "clob", "string", "citext", "varchar2"
            ):
                unsupported.append({
                    "item": f"{table['table']}.{column['name']}",
                    "reason": f"unmapped SQL type '{column['sql_type']}'; seed value falls back to a string literal",
                })

    if schema_files and not tables:
        unknown.append({
            "item": "SQL schema parse",
            "reason": f"no CREATE TABLE statements parsed from {', '.join(schema_files)}",
        })

    env = _env_from_files(root, profile)
    endpoints = _openapi_endpoints(root, profile)

    ports = []
    for stack in profile.get("stacks", []):
        if stack.get("default_port"):
            ports.append({
                "stack": stack["id"],
                "default_port": stack["default_port"],
                "bind": "127.0.0.1",
                "allocation": "dynamic-if-busy",
            })

    stub_upstreams = []
    for store in profile.get("datastores", []):
        if store["engine"] in ("kafka", "rabbitmq", "redis"):
            stub_upstreams.append({
                "id": f"stub.{store['engine']}",
                "engine": store["engine"],
                "mode": "container" if store["engine"] != "redis" else "container",
                "required_for_readiness": True,
            })
    if any(s.get("family") == "b32" for s in profile.get("stacks", [])):
        stub_upstreams.append({
            "id": "stub.api",
            "engine": "http-mock",
            "mode": "in-process",
            "required_for_readiness": True,
            "note": "client stacks need a deterministic API stub before a page can render seeded data",
        })

    payload: dict[str, Any] = {
        "schema": f"{SCHEMA_PREFIX}.minimal-data-requirements/1",
        "generated_at": utc_now(),
        "profile_digest": profile.get("profile_digest"),
        "definition": (
            "The smallest environment, dataset and stub set required to reach readiness "
            "and serve one functional request. Not a test corpus."
        ),
        "environment": env,
        "datasets": datasets,
        "stub_upstreams": stub_upstreams,
        "ports": ports,
        "candidate_smoke_endpoints": endpoints,
        "unsupported": unsupported,
        "unknown": unknown,
    }
    payload["requirements_digest"] = canonical_digest(
        {k: v for k, v in payload.items() if k not in ("generated_at", "requirements_digest")}
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive minimal runtime data requirements")
    parser.add_argument("project_root")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = Path(args.project_root)
    profile_path = smoke_dir(root) / "profile.json"
    if not profile_path.is_file():
        print(f"error: missing {profile_path}; run detect_project_profile.py --write first")
        return 2
    payload = derive(root, read_json(profile_path))
    if args.write:
        path = write_json(smoke_dir(root) / "minimal-data-requirements.json", payload)
        print(f"wrote {path}")
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
