#!/usr/bin/env python3
"""Static contract validation for the Elmos large-repository PostgreSQL design.

This does not replace executing migrations against a real PostgreSQL 16/17
instance. It catches structural drift, unknown references, missing uniqueness,
missing RLS/gate contracts, unsafe destructive DDL and packaging errors.
"""
from __future__ import annotations

import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "database" / "migrations"
ERRORS: list[str] = []
WARNINGS: list[str] = []

EXPECTED_MIGRATIONS = [
    "V001__extensions_schemas_and_helpers.sql",
    "V010__tenancy_projects_jobs_and_admission.sql",
    "V020__runs_tasks_sessions_and_recovery.sql",
    "V030__artifacts_manifests_staging_and_checkpoints.sql",
    "V040__repository_intelligence_semantic_ir_and_capabilities.sql",
    "V045__project_generation_and_transformation.sql",
    "V050__verification_evidence_gates_and_repair.sql",
    "V060__model_tool_metering_cost_eta_and_cache.sql",
    "V070__integration_learning_deployment_and_audit.sql",
    "V080__cross_links_rls_and_read_models.sql",
    "V090__transactional_runtime_functions.sql",
]
REQUIRED_SCHEMAS = {
    "core", "exec", "artifact", "analysis", "generation", "transform",
    "verify", "metering", "cache", "integration", "learning", "ops", "audit",
}
REQUIRED_TABLES = {
    "core.account_task_slot", "core.job", "exec.run", "exec.task", "exec.task_attempt",
    "exec.execution_lease", "exec.run_event", "exec.session_event", "exec.checkpoint",
    "artifact.object_blob", "artifact.artifact", "artifact.manifest", "artifact.staged_object",
    "analysis.repository_file", "analysis.symbol_record", "analysis.semantic_ir_revision",
    "analysis.capability", "generation.requirement_node", "generation.project_generation_plan",
    "generation.generated_file", "transform.transformation_plan", "transform.target_revision",
    "verify.requirement_coverage", "verify.capability_coverage", "verify.evidence_item",
    "verify.evidence_bundle", "verify.gate_evaluation", "verify.semantic_gap",
    "metering.model_invocation", "metering.tool_invocation", "metering.cost_ledger",
    "metering.eta_forecast", "cache.cache_entry", "integration.side_effect_receipt",
    "integration.outbox_event", "learning.rule_candidate", "learning.rule_release",
    "ops.release_component", "ops.deployment", "ops.deployment_gate", "audit.audit_event",
}
REQUIRED_FUNCTIONS = {
    "core.claim_account_slot", "core.renew_account_slot", "core.release_account_slot",
    "exec.create_run", "exec.append_run_event", "exec.append_session_event",
    "exec.claim_ready_task", "exec.renew_task_lease", "exec.finish_task_attempt",
    "exec.seal_checkpoint", "integration.reserve_side_effect",
    "verify.complete_run_with_gate", "ops.complete_deployment_with_gate",
}
REQUIRED_VIEWS = {
    "core.v_account_slot_usage", "exec.v_run_dashboard", "exec.v_stalled_task_attempts",
    "analysis.v_repository_inventory", "verify.v_completion_readiness",
    "metering.v_run_financials", "cache.v_run_cache_effectiveness",
    "ops.v_deployment_readiness",
}

REQUIRED_SUPPORTING_FILES = [
    "database/README.md",
    "database/EXECUTIVE-SUMMARY.md",
    "database/TABLE-CATALOG.md",
    "database/DB-1-MINIMUM-TABLE-SET.md",
    "database/roles/README.md",
    "database/roles/roles-and-grants.example.sql",
    "database/queries/role_hardening_check.sql",
    "VALIDATION-REPORT.md",
    "database/queries/operator_queries.sql",
    "database/tests/invariants.sql",
    "database/tests/concurrency-scenarios.md",
    "database/mermaid/large-run-erd.mmd",
    "docs/DATABASE-DESIGN-LARGE-REPOSITORY-RUNS.md",
    "docs/DATABASE-TRANSACTION-AND-RECOVERY.md",
    "docs/DATABASE-PARTITIONING-RETENTION.md",
    "docs/DATABASE-SECURITY-RLS.md",
    "docs/DATABASE-MIGRATION-OPERATIONS.md",
    "skills/large-repository-run-persistence/SKILL.md",
]


def strip_line_comments(text: str) -> str:
    return re.sub(r"--.*$", "", text, flags=re.MULTILINE)


def extract_create_table_blocks(text: str) -> dict[str, str]:
    """Return parent CREATE TABLE bodies using a quote-aware parenthesis scanner."""
    clean = strip_line_comments(text)
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?![^;\n]*PARTITION\s+OF)"
        r"(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\s*\(",
        re.IGNORECASE,
    )
    blocks: dict[str, str] = {}
    for match in pattern.finditer(clean):
        name = match.group(1).lower()
        start = match.end() - 1
        depth = 0
        quote: str | None = None
        i = start
        while i < len(clean):
            char = clean[i]
            if quote:
                if char == quote:
                    if i + 1 < len(clean) and clean[i + 1] == quote:
                        i += 2
                        continue
                    quote = None
            else:
                if char in {"'", '"'}:
                    quote = char
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                    if depth == 0:
                        break
            i += 1
        else:
            ERRORS.append(f"unterminated CREATE TABLE body: {name}")
            continue
        if name in blocks:
            ERRORS.append(f"duplicate CREATE TABLE: {name}")
        blocks[name] = clean[start + 1 : i]
    return blocks


def normalized_columns(value: str) -> tuple[str, ...]:
    return tuple(part.strip().strip('"').lower() for part in value.split(","))


def collect_unique_keys(blocks: dict[str, str], all_sql: str) -> dict[str, set[tuple[str, ...]]]:
    unique: dict[str, set[tuple[str, ...]]] = collections.defaultdict(set)
    for table, body in blocks.items():
        for match in re.finditer(r"PRIMARY\s+KEY\s*\(([^)]+)\)", body, re.IGNORECASE):
            unique[table].add(normalized_columns(match.group(1)))
        for match in re.finditer(
            r"UNIQUE(?:\s+NULLS\s+NOT\s+DISTINCT)?\s*\(([^)]+)\)", body, re.IGNORECASE
        ):
            unique[table].add(normalized_columns(match.group(1)))
        for line in body.splitlines():
            upper = line.upper()
            before = upper.split("PRIMARY KEY", 1)[0] if "PRIMARY KEY" in upper else ""
            if "PRIMARY KEY" in upper and "(" not in before:
                candidate = line.strip().split()[0].strip('"').rstrip(",").lower()
                if re.fullmatch(r"[a-z_][a-z0-9_]*", candidate):
                    unique[table].add((candidate,))
    for match in re.finditer(
        r"ALTER\s+TABLE\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\s+"
        r"ADD\s+(?:CONSTRAINT\s+[a-z_][a-z0-9_]*\s+)?UNIQUE\s*\(([^)]+)\)",
        all_sql,
        re.IGNORECASE,
    ):
        unique[match.group(1).lower()].add(normalized_columns(match.group(2)))
    return unique


def collect_foreign_keys(blocks: dict[str, str], all_sql: str) -> list[tuple[str, str, tuple[str, ...]]]:
    foreign_keys: list[tuple[str, str, tuple[str, ...]]] = []
    for source, body in blocks.items():
        for match in re.finditer(
            r"FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+"
            r"([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\s*\(([^)]+)\)",
            body,
            re.IGNORECASE,
        ):
            foreign_keys.append((source, match.group(2).lower(), normalized_columns(match.group(3))))
        for match in re.finditer(
            r"^\s*[a-z_][a-z0-9_]*\s+[^,\n]*?\sREFERENCES\s+"
            r"([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\s*\(([^)]+)\)",
            body,
            re.IGNORECASE | re.MULTILINE,
        ):
            foreign_keys.append((source, match.group(1).lower(), normalized_columns(match.group(2))))
    for statement in re.findall(r"ALTER\s+TABLE\s+.*?;", all_sql, flags=re.IGNORECASE | re.DOTALL):
        source_match = re.match(
            r"ALTER\s+TABLE\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)", statement, re.IGNORECASE
        )
        if not source_match:
            continue
        source = source_match.group(1).lower()
        for match in re.finditer(
            r"FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+"
            r"([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\s*\(([^)]+)\)",
            statement,
            re.IGNORECASE,
        ):
            foreign_keys.append((source, match.group(2).lower(), normalized_columns(match.group(3))))
    return foreign_keys



def split_top_level_items(body: str) -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    i = 0
    while i < len(body):
        char = body[i]
        if quote:
            if char == quote:
                if i + 1 < len(body) and body[i + 1] == quote:
                    i += 2
                    continue
                quote = None
        else:
            if char in {"'", '"'}:
                quote = char
            elif char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            elif char == ',' and depth == 0:
                items.append(body[start:i].strip())
                start = i + 1
        i += 1
    items.append(body[start:].strip())
    return [item for item in items if item]


def collect_table_columns(blocks: dict[str, str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    constraint_words = {"constraint", "primary", "unique", "foreign", "check", "exclude"}
    for table, body in blocks.items():
        columns: set[str] = set()
        for item in split_top_level_items(body):
            token = item.split(None, 1)[0].strip('"').lower()
            if token not in constraint_words and re.fullmatch(r"[a-z_][a-z0-9_]*", token):
                columns.add(token)
        result[table] = columns
    return result


def scan_to_top_level_keyword(text: str, start: int, keyword: str) -> int | None:
    depth = 0
    quote: str | None = None
    dollar_tag: str | None = None
    i = start
    pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    while i < len(text):
        if dollar_tag:
            if text.startswith(dollar_tag, i):
                i += len(dollar_tag)
                dollar_tag = None
                continue
            i += 1
            continue
        char = text[i]
        if quote:
            if char == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        dollar = re.match(r"\$[A-Za-z_0-9]*\$", text[i:])
        if dollar:
            dollar_tag = dollar.group(0)
            i += len(dollar_tag)
            continue
        if char in {"'", '"'}:
            quote = char
            i += 1
            continue
        if char == '(':
            depth += 1
            i += 1
            continue
        if char == ')':
            depth -= 1
            i += 1
            continue
        if depth == 0:
            match = pattern.match(text, i)
            if match:
                return i
        i += 1
    return None


def collect_view_columns(all_sql: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    pattern = re.compile(
        r"CREATE\s+VIEW\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)\b.*?\bAS\b",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(all_sql):
        view = match.group(1).lower()
        select_pos = scan_to_top_level_keyword(all_sql, match.end(), "SELECT")
        if select_pos is None:
            continue
        from_pos = scan_to_top_level_keyword(all_sql, select_pos + len("SELECT"), "FROM")
        if from_pos is None:
            continue
        select_list = all_sql[select_pos + len("SELECT"):from_pos]
        columns: set[str] = set()
        for item in split_top_level_items(select_list):
            alias = re.search(r"\bAS\s+([a-z_][a-z0-9_]*)\s*$", item, re.IGNORECASE)
            if alias:
                columns.add(alias.group(1).lower())
                continue
            simple = re.search(r"(?:^|\.)\b([a-z_][a-z0-9_]*)\s*$", item.strip(), re.IGNORECASE)
            if simple:
                columns.add(simple.group(1).lower())
        result[view] = columns
    return result


def split_sql_statements(text: str) -> list[str]:
    statements: list[str] = []
    start = 0
    quote: str | None = None
    dollar_tag: str | None = None
    i = 0
    while i < len(text):
        if dollar_tag:
            if text.startswith(dollar_tag, i):
                i += len(dollar_tag)
                dollar_tag = None
                continue
            i += 1
            continue
        char = text[i]
        if quote:
            if char == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        dollar = re.match(r"\$[A-Za-z_0-9]*\$", text[i:])
        if dollar:
            dollar_tag = dollar.group(0)
            i += len(dollar_tag)
            continue
        if char in {"'", '"'}:
            quote = char
        elif char == ';':
            statements.append(text[start:i + 1])
            start = i + 1
        i += 1
    if text[start:].strip():
        statements.append(text[start:])
    return statements


def validate_statement_columns(
    source_name: str,
    statement_no: int,
    statement: str,
    relation_columns: dict[str, set[str]],
) -> None:
    aliases: dict[str, str] = {}
    subquery_aliases = {
        match.group(1).lower()
        for match in re.finditer(r"\)\s+(?:AS\s+)?([a-z_][a-z0-9_]*)\s+(?:ON|WHERE|JOIN|LEFT|RIGHT|FULL|CROSS|ORDER|GROUP|LIMIT|;)", statement, re.IGNORECASE)
    }
    for match in re.finditer(
        r"\b(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)"
        r"(?:\s+(?:AS\s+)?([a-z_][a-z0-9_]*))?",
        statement,
        re.IGNORECASE,
    ):
        relation = match.group(1).lower()
        alias = (match.group(2) or relation.split(".", 1)[1]).lower()
        if relation in relation_columns and alias not in subquery_aliases:
            aliases[alias] = relation
    for match in re.finditer(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", statement, re.IGNORECASE):
        alias, column = match.group(1).lower(), match.group(2).lower()
        relation = aliases.get(alias)
        if relation and column not in relation_columns[relation]:
            ERRORS.append(
                f"{source_name}: statement {statement_no} references unknown column "
                f"{alias}.{column} on {relation}; known={sorted(relation_columns[relation])}"
            )


def validate_operator_query_columns(
    path: Path,
    table_columns: dict[str, set[str]],
    view_columns: dict[str, set[str]],
) -> None:
    relation_columns = {**table_columns, **view_columns}
    text = strip_line_comments(path.read_text(encoding="utf-8"))
    for statement_no, statement in enumerate(split_sql_statements(text), start=1):
        validate_statement_columns(path.name, statement_no, statement, relation_columns)


def validate_invariant_query_columns(
    path: Path,
    table_columns: dict[str, set[str]],
    view_columns: dict[str, set[str]],
) -> None:
    relation_columns = {**table_columns, **view_columns}
    text = strip_line_comments(path.read_text(encoding="utf-8"))
    pieces: list[str] = []
    for match in re.finditer(r"DO\s+\$\$(.*?)\$\$\s*;", text, re.IGNORECASE | re.DOTALL):
        pieces.extend(split_sql_statements(match.group(1)))
    outside = re.sub(r"DO\s+\$\$.*?\$\$\s*;", "", text, flags=re.IGNORECASE | re.DOTALL)
    pieces.extend(split_sql_statements(outside))
    for statement_no, statement in enumerate(pieces, start=1):
        validate_statement_columns(path.name, statement_no, statement, relation_columns)


def validate_dollar_quotes(path: Path, text: str) -> None:
    tags = re.findall(r"\$[A-Za-z_0-9]*\$", text)
    counts = collections.Counter(tags)
    for tag, count in counts.items():
        if count % 2:
            ERRORS.append(f"{path.name}: unbalanced dollar quote {tag} ({count})")


for rel in REQUIRED_SUPPORTING_FILES:
    if not (ROOT / rel).exists():
        ERRORS.append(f"missing supporting file: {rel}")

migration_files = sorted(MIGRATIONS.glob("V*.sql"))
actual_names = [path.name for path in migration_files]
if actual_names != EXPECTED_MIGRATIONS:
    ERRORS.append(f"migration order mismatch: {actual_names}")

texts: list[str] = []
for path in migration_files:
    text = path.read_text(encoding="utf-8")
    texts.append(text)
    if len(re.findall(r"^BEGIN;$", text, flags=re.MULTILINE)) != 1:
        ERRORS.append(f"{path.name}: expected exactly one transaction BEGIN")
    if len(re.findall(r"^COMMIT;$", text, flags=re.MULTILINE)) != 1:
        ERRORS.append(f"{path.name}: expected exactly one transaction COMMIT")
    if re.search(r"\b(DROP\s+(TABLE|SCHEMA)|TRUNCATE\s+TABLE)\b", text, re.IGNORECASE):
        ERRORS.append(f"{path.name}: destructive DDL found")
    validate_dollar_quotes(path, text)

all_sql = "\n".join(texts)
blocks = extract_create_table_blocks(all_sql)
table_columns = collect_table_columns(blocks)
view_columns = collect_view_columns(all_sql)
unique_keys = collect_unique_keys(blocks, all_sql)
foreign_keys = collect_foreign_keys(blocks, all_sql)

if len(blocks) != 136:
    ERRORS.append(f"expected v1.1.0 reference model to contain exactly 136 parent tables, got {len(blocks)}")
if not REQUIRED_TABLES.issubset(blocks):
    ERRORS.append(f"missing required tables: {sorted(REQUIRED_TABLES - set(blocks))}")

schemas = set(re.findall(r"CREATE\s+SCHEMA\s+IF\s+NOT\s+EXISTS\s+([a-z_][a-z0-9_]*)", all_sql, re.IGNORECASE))
if not REQUIRED_SCHEMAS.issubset({s.lower() for s in schemas}):
    ERRORS.append(f"missing schemas: {sorted(REQUIRED_SCHEMAS - {s.lower() for s in schemas})}")

for source, target, target_columns in foreign_keys:
    if target not in blocks:
        ERRORS.append(f"{source}: FK references unknown table {target}")
        continue
    if target_columns not in unique_keys[target]:
        ERRORS.append(
            f"{source}: FK target {target}{target_columns} is not a declared PK/UNIQUE; "
            f"known={sorted(unique_keys[target])}"
        )

catalog_text = (ROOT / "database" / "TABLE-CATALOG.md").read_text(encoding="utf-8")
for table in blocks:
    if f"`{table}`" not in catalog_text:
        ERRORS.append(f"table missing from TABLE-CATALOG.md: {table}")

for table, body in blocks.items():
    schema = table.split(".", 1)[0]
    if schema in REQUIRED_SCHEMAS and table != "core.tenant" and "tenant_id" not in body:
        ERRORS.append(f"tenant-scoped table missing tenant_id: {table}")

functions = {
    name.lower()
    for name in re.findall(
        r"CREATE\s+OR\s+REPLACE\s+FUNCTION\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)",
        all_sql,
        re.IGNORECASE,
    )
}
if not REQUIRED_FUNCTIONS.issubset(functions):
    ERRORS.append(f"missing runtime functions: {sorted(REQUIRED_FUNCTIONS - functions)}")

views = {
    name.lower()
    for name in re.findall(r"CREATE\s+VIEW\s+([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)", all_sql, re.IGNORECASE)
}
if not REQUIRED_VIEWS.issubset(views):
    ERRORS.append(f"missing read-model views: {sorted(REQUIRED_VIEWS - views)}")

contract_checks = {
    "exactly three account slots": all(token in all_sql for token in ["NEW.id, 1", "NEW.id, 2", "NEW.id, 3"]),
    "account concurrency capped at three": "concurrency_limit BETWEEN 0 AND 3" in all_sql,
    "slot generation fencing": "lease_generation = lease_generation + 1" in all_sql,
    "one active execution lease": "execution_lease_one_active_idx" in all_sql,
    "run event hash chain": "previous_event_hash" in blocks["exec.run_event"] and "event_hash" in blocks["exec.run_event"],
    "session event hash chain": "previous_event_hash" in blocks["exec.session_event"] and "event_hash" in blocks["exec.session_event"],
    "event immutability": "run_event_immutable" in all_sql and "session_event_immutable" in all_sql,
    "checkpoint seal": "CREATE OR REPLACE FUNCTION exec.seal_checkpoint" in all_sql,
    "checkpoint seal revoked from PUBLIC": "REVOKE ALL ON FUNCTION exec.seal_checkpoint(uuid, uuid) FROM PUBLIC" in all_sql,
    "side effect reservation revoked from PUBLIC": "REVOKE ALL ON FUNCTION integration.reserve_side_effect" in all_sql,
    "side-effect unknown result": "unknown_result" in blocks["integration.side_effect_receipt"],
    "P05 exact revision binding": "gate revision binding does not match run" in all_sql,
    "P05 revoked/stale evidence rejection": "foreign, revoked or stale evidence" in all_sql,
    "P05 authoritative coverage check": "authoritative coverage ledgers" in all_sql,
    "P05 non-vacuous ledgers": "requires non-empty requirement and capability ledgers" in all_sql,
    "P05 current-run-only job completion": "current_run_id = p_run_id" in all_sql,
    "evidence revocation timestamp": "revoked_at" in table_columns.get("verify.evidence_revocation", set()),
    "P05 unfinished task check": "v_unfinished" in all_sql,
    "P05 unresolved side effect check": "v_side_effects" in all_sql,
    "deployment image digest check": "wrong image digest" in all_sql,
    "deployment migration check": "required database migration has not succeeded" in all_sql,
    "FORCE RLS": "FORCE ROW LEVEL SECURITY" in all_sql,
    "RLS covers all commercial schemas": all(f"'{schema}'" in all_sql for schema in REQUIRED_SCHEMAS),
    "security-invoker views": all_sql.count("security_invoker = true") >= len(REQUIRED_VIEWS),
    "machine ETA separated": "machine_wall_clock_remaining_p50_seconds" in blocks["metering.eta_forecast"],
    "human equivalent separated": "human_equivalent_p50_hours" in blocks["metering.eta_forecast"],
    "HITL wait separated": "expected_hitl_wait_seconds" in blocks["metering.eta_forecast"],
}
for label, passed in contract_checks.items():
    if not passed:
        ERRORS.append(f"missing contract: {label}")

for table in ("metering.usage_ledger", "metering.cost_ledger", "metering.revenue_ledger", "audit.audit_event"):
    short = table.split(".", 1)[1]
    if f"{short}_immutable" not in all_sql:
        ERRORS.append(f"append-only trigger missing for {table}")

# Large bodies must be externalized. These explicit anti-patterns must never be introduced.
for forbidden in (
    r"\bsource_code\s+(text|bytea)",
    r"\bfull_ast\s+(jsonb|text|bytea)",
    r"\braw_model_output\s+(text|bytea)",
    r"\bcomplete_stdout\s+(text|bytea)",
):
    if re.search(forbidden, all_sql, re.IGNORECASE):
        ERRORS.append(f"large-body anti-pattern found: {forbidden}")

validate_operator_query_columns(
    ROOT / "database" / "queries" / "operator_queries.sql",
    table_columns,
    view_columns,
)
validate_invariant_query_columns(
    ROOT / "database" / "tests" / "invariants.sql",
    table_columns,
    view_columns,
)

operator_text = (ROOT / "database" / "queries" / "operator_queries.sql").read_text(encoding="utf-8")
for stale in ("a.status AS artifact_status", "rc.component_name", "r.created_at >= g.evaluated_at"):
    if stale in operator_text:
        ERRORS.append(f"operator query contains stale column contract: {stale}")

schema_counts = collections.Counter(table.split(".", 1)[0] for table in blocks)
if ERRORS:
    print("DATABASE DESIGN VALIDATION FAILED")
    for error in ERRORS:
        print(f"- {error}")
    sys.exit(1)

print("DATABASE DESIGN VALIDATION PASSED")
print(f"migrations={len(migration_files)}")
print(f"parent_tables={len(blocks)}")
print(f"foreign_keys_checked={len(foreign_keys)}")
print(f"functions={len(functions)}")
print(f"views={len(views)}")
print("tables_by_schema=" + ",".join(f"{k}:{schema_counts[k]}" for k in sorted(schema_counts)))
for warning in WARNINGS:
    print(f"WARNING: {warning}")
