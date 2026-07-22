#!/usr/bin/env python3
"""Generate additive, tenant-scoped persistence for product Batches 27-34."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "ChatGPT-Git项目商业化模式 (1).md"
TARGET = ROOT / "modules" / "persistence" / "src" / "main" / "resources" / "db" / "migration"


def block_at(lines: list[str], heading_line: int) -> list[str]:
    index = heading_line - 1
    while index < len(lines) and lines[index].strip() != "```text":
        index += 1
    if index == len(lines):
        raise RuntimeError(f"text block not found after line {heading_line}")
    index += 1
    result: list[str] = []
    while index < len(lines) and lines[index].strip() != "```":
        value = lines[index].strip()
        if value:
            result.append(value.removeprefix("iam."))
        index += 1
    return result


def sql(batch: int, schema: str, tables: list[str], title: str) -> str:
    unique = list(dict.fromkeys(tables))
    values = ",\n        ".join(f"'{value}'" for value in unique)
    return f"""-- ELMOS Product Batch {batch}: {title}.
-- Records are evidence-bound and append-only. This schema does not execute external actions.

CREATE SCHEMA IF NOT EXISTS {schema};

DO $$
DECLARE
    target_schema text := '{schema}';
    table_name text;
    batch_tables text[] := ARRAY[
        {values}
    ];
BEGIN
    FOREACH table_name IN ARRAY batch_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'domain_run_id varchar(160) NOT NULL,' ||
            'snapshot_digest varchar(64) NOT NULL CHECK (snapshot_digest ~ ''^[0-9a-f]{{64}}$''),' ||
            'policy_version varchar(96) NOT NULL,' ||
            'human_owner_id varchar(160) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''NOT_RUN'' CHECK (status IN (''OBSERVED'',''NOT_RUN'',''INCONCLUSIVE'',''BLOCKED'',''READY_FOR_HUMAN_DECISION'')),' ||
            'independent_judge boolean NOT NULL DEFAULT false,' ||
            'critical_open_risks integer NOT NULL DEFAULT 0 CHECK (critical_open_risks >= 0),' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb CHECK (jsonb_typeof(evidence_refs) = ''array''),' ||
            'payload jsonb NOT NULL DEFAULT ''{{}}''::jsonb CHECK (jsonb_typeof(payload) = ''object''),' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'human_approval_ref varchar(512),' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'CHECK (status <> ''READY_FOR_HUMAN_DECISION'' OR (independent_judge AND critical_open_risks = 0 AND jsonb_array_length(evidence_refs) > 0)),' ||
            'CHECK (human_approval_ref IS NULL OR jsonb_array_length(evidence_refs) > 0),' ||
            'UNIQUE (organization_id, idempotency_key))',
            target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id, domain_run_id, status)',
                       'idx_' || left(table_name, 38) || '_roadmap_run', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            target_schema, table_name);
        EXECUTE format(
            'CREATE TRIGGER product_governance_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
            target_schema, table_name);
    END LOOP;
END;
$$;
"""


def main() -> None:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    batches: dict[int, tuple[str, str, list[str]]] = {
        27: ("technology_business_management", "technology business management and investment governance", block_at(lines, 24411)),
        28: ("organization_workforce", "organization capability and workforce modernization", block_at(lines, 29877)),
        29: ("transformation_execution", "enterprise transformation execution and change management", block_at(lines, 35432)),
        30: ("autonomous_control_tower", "autonomous modernization control tower", block_at(lines, 40685)),
        31: ("mvp_engineering", "reference implementation and MVP engineering", [
            "repositories", "migration_projects", "migration_events", "runner_registrations", "runner_tasks",
            "agent_runs", "webhook_deliveries", "audit_events", "outbox_events", "repository_snapshots",
            "baseline_builds", "java_health_reports", "migration_plans", "rewrite_runs", "verification_runs",
            "pull_request_deliveries", "evidence_packs", "security_findings", "idempotency_records", "readiness_reviews",
        ]),
        32: ("mvp_gap_review", "independent MVP gap review and remediation", [
            "claimed_artifacts", "claimed_validations", "rerun_validations", "gap_findings", "security_gaps",
            "workflow_gaps", "runner_gaps", "java_capability_gaps", "supply_chain_gaps", "remediation_actions",
            "remediation_evidence", "readiness_reviews",
        ]),
        33: ("secure_java_vertical", "secure Java modernization paid vertical loop", [
            "identity_contexts", "runner_enrollments", "runner_leases", "sandbox_executions", "repository_snapshots",
            "maven_baselines", "java_health_reports", "migration_plans", "rewrite_runs", "compatibility_runs",
            "agent_repair_runs", "temporal_workflows", "pull_request_deliveries", "evidence_packs",
            "release_gates", "commercial_readiness_reviews",
        ]),
        34: ("identity_access_governance", "enterprise identity, multitenancy and access governance",
             block_at(lines, 59020) + block_at(lines, 64791) + block_at(lines, 68465)),
    }
    filenames = {
        27: "V33__technology_business_management.sql",
        28: "V34__organization_workforce_modernization.sql",
        29: "V35__transformation_execution_change_management.sql",
        30: "V36__autonomous_modernization_control_tower.sql",
        31: "V37__reference_mvp_engineering.sql",
        32: "V38__mvp_gap_review_remediation.sql",
        33: "V39__secure_java_vertical_loop.sql",
        34: "V40__enterprise_identity_access_governance.sql",
    }
    for batch, (schema, title, tables) in batches.items():
        (TARGET / filenames[batch]).write_text(sql(batch, schema, tables, title), encoding="utf-8")
        print(batch, schema, len(set(tables)))


if __name__ == "__main__":
    main()
