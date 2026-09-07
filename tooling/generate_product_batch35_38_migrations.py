#!/usr/bin/env python3
"""Generate exact, tenant-scoped persistence projections for Product B35-B38.

Product batches are deliberately separate from the Migration Pack M35-M45
namespace. The commercial specification is the source of the qualified table
families; this generator does not infer or silently drop a listed table.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/stephen/Downloads/ChatGPT-Git项目商业化模式 (2).md")
TARGET = ROOT / "modules" / "persistence" / "src" / "main" / "resources" / "db" / "migration"
QUALIFIED_TABLE = re.compile(r"^([a-z_]+)\.([a-z0-9_]+)$")

SPECS = (
    (42, "B35", ((22700, 22811), (27380, 27480), (32556, 32723)), "product_source_control_and_workspace"),
    (43, "B36", ((38222, 38391), (44440, 44611), (50381, 50595)), "product_secure_execution_plane"),
    (44, "B37A", ((55449, 55673),), "product_artifact_evidence_fabric"),
    (45, "B37B", ((59605, 59807),), "product_external_evidence_producers"),
    (46, "B37C", ((63741, 64007),), "product_assurance_analytics"),
    (47, "B38A", ((68047, 68303),), "product_continuous_authorization"),
)


def tables(lines: list[str], start: int, end: int) -> list[tuple[str, str]]:
    selected: list[tuple[str, str]] = []
    for value in lines[start - 1 : end - 1]:
        match = QUALIFIED_TABLE.fullmatch(value.strip())
        if match:
            selected.append((match.group(1), match.group(2)))
    return list(dict.fromkeys(selected))


def sql(version: int, batch: str, values: list[tuple[str, str]]) -> str:
    rows = ",\n        ".join(f"('{schema}', '{table}')" for schema, table in values)
    policy = f"product_{batch.lower()}_tenant_isolation".replace("-", "_")
    trigger = f"product_{batch.lower()}_append_only".replace("-", "_")
    return f"""-- ELMOS Product {batch}: exact evidence projection generated from the commercial specification.
-- This migration records readiness and evidence only; external operations remain NOT_RUN.

DO $$
DECLARE
    target record;
BEGIN
    FOR target IN SELECT * FROM (VALUES
        {rows}
    ) AS listed(schema_name, table_name)
    LOOP
        EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', target.schema_name);
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'domain_run_id varchar(160) NOT NULL,' ||
            'subject_digest varchar(64) NOT NULL CHECK (subject_digest ~ ''^[0-9a-f]{{64}}$''),' ||
            'context_snapshot_digest varchar(64) NOT NULL CHECK (context_snapshot_digest ~ ''^[0-9a-f]{{64}}$''),' ||
            'policy_version varchar(96) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''NOT_RUN'' CHECK (status IN (''OBSERVED'',''VERIFIED'',''FAILED'',''NOT_RUN'',''INCONCLUSIVE'',''UNKNOWN'',''BLOCKED'',''READY_FOR_EXTERNAL_GATE'',''READY_FOR_HUMAN_DECISION'')),' ||
            'independent_verifier_id varchar(160),' ||
            'critical_open_risks integer NOT NULL DEFAULT 0 CHECK (critical_open_risks >= 0),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{{}}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'human_approval_ref varchar(512),' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (status <> ''READY_FOR_HUMAN_DECISION'' OR (independent_verifier_id IS NOT NULL AND critical_open_risks = 0 AND jsonb_array_length(evidence_refs) > 0)),' ||
            'CHECK (human_approval_ref IS NULL OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, idempotency_key))',
            target.schema_name, target.table_name);
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I.%I (organization_id, domain_run_id, status)',
            'idx_' || left(target.table_name, 32) || '_' || substr(md5(target.schema_name || target.table_name), 1, 8),
            target.schema_name, target.table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target.schema_name, target.table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target.schema_name, target.table_name);
        IF NOT EXISTS (
            SELECT 1 FROM pg_policies
            WHERE schemaname = target.schema_name AND tablename = target.table_name AND policyname = '{policy}'
        ) THEN
            EXECUTE format(
                'CREATE POLICY {policy} ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
                target.schema_name, target.table_name);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger trigger
            JOIN pg_class relation ON relation.oid = trigger.tgrelid
            JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
            WHERE namespace.nspname = target.schema_name AND relation.relname = target.table_name
              AND trigger.tgname = '{trigger}' AND NOT trigger.tgisinternal
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER {trigger} BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target.schema_name, target.table_name);
        END IF;
    END LOOP;
END;
$$;
"""


def main() -> None:
    if not SOURCE.is_file():
        raise SystemExit(f"commercial specification is missing: {SOURCE}")
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    counts: dict[str, int] = {}
    for version, batch, ranges, slug in SPECS:
        selected = list(dict.fromkeys(
            table for start, end in ranges for table in tables(lines, start, end)
        ))
        if not selected:
            raise SystemExit(f"no qualified tables found for {batch}")
        path = TARGET / f"V{version}__{slug}.sql"
        path.write_text(sql(version, batch, selected), encoding="utf-8")
        counts[batch] = len(selected)
    print(" ".join(f"{batch}={count}" for batch, count in counts.items()))


if __name__ == "__main__":
    main()
