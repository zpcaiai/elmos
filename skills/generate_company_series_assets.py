#!/usr/bin/env python3
"""Generate the additive Batch 15-18 company-series Skill assets from authority texts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


SKILL_HEADING = re.compile(r"^# Skill (\d+)[：:](.+?)\s*$", re.MULTILINE)
TOP_HEADING = re.compile(r"^# (?!Skill )", re.MULTILINE)


@dataclass(frozen=True)
class Batch:
    number: int
    first: int
    last: int
    group: str
    title: str
    model: str
    final_gate: str
    final_status: str
    reference: str
    checklist: str


BATCHES = {
    15: Batch(15, 461, 525, "company-operating-system",
              "Company Operating and Governance System", "COGS", "C15-G",
              "company-scale-operating-ready",
              "batch-15-company-evidence-boundary.md",
              "batch-15-company-operating-acceptance-checklist.md"),
    16: Batch(16, 526, 592, "agent-workforce",
              "AI-native company and Agent Workforce", "AI-native operating system",
              "AI16-G", "bounded-autonomous-company-ready",
              "batch-16-agent-workforce-evidence-boundary.md",
              "batch-16-agent-workforce-acceptance-checklist.md"),
    17: Batch(17, 593, 668, "vertical-solutions",
              "Vertical Solution Factory", "VSP four-layer model", "V17-G",
              "vertical-commercial-delivery-ready",
              "batch-17-vertical-solution-evidence-boundary.md",
              "batch-17-vertical-solution-acceptance-checklist.md"),
    18: Batch(18, 669, 745, "group-integration",
              "Group Integration Factory", "GITM", "M18-H",
              "group-integration-completed",
              "batch-18-group-integration-evidence-boundary.md",
              "batch-18-group-integration-acceptance-checklist.md"),
}

SCHEMA_GROUPS = {
    15: "company-operating-system-schema",
    16: "agent-workforce-schema",
    17: "vertical-solution-schema",
    18: "group-integration-schema",
}

GATES = {
    15: ["C15-A", "C15-B", "C15-C", "C15-D", "C15-E", "C15-F", "C15-G"],
    16: ["AI16-A", "AI16-B", "AI16-C", "AI16-D", "AI16-E", "AI16-F", "AI16-G"],
    17: ["V17-A", "V17-B", "V17-C", "V17-D", "V17-E", "V17-F", "V17-G"],
    18: ["M18-A", "M18-B", "M18-C", "M18-D", "M18-E", "M18-F", "M18-G", "M18-H"],
}

DIMENSIONS = {
    15: ["purpose-strategy", "strategic-execution", "organization-talent",
         "financial-management", "capital-fundraising", "governance",
         "enterprise-risk", "board-operations"],
    16: ["human-governance", "company-constitution", "autonomous-operations",
         "agent-workforce", "human-workforce", "action-tools", "evidence-evaluation",
         "learning-correction"],
    17: ["shared-core", "industry-base-pack", "jurisdiction-overlay",
         "customer-extension", "finance", "manufacturing", "energy", "healthcare",
         "government", "commerce", "telecom"],
    18: ["business-capability", "application-portfolio", "data-domain", "identity",
         "integration", "technology-standards", "infrastructure", "operating-model",
         "governance", "synergy"],
}

PERSISTENCE = {
    15: (24, "company_ops", "company_operating_and_governance_system",
         ["decision_logs", "okr_updates", "operating_reviews", "actuals", "variance_analyses",
          "investor_interactions", "equity_events", "control_evidence", "board_resolutions",
          "board_minutes", "board_actions"]),
    16: (25, "agent_workforce", "ai_native_company_and_agent_workforce",
         ["agent_lifecycle_events", "agent_actions", "agent_observations", "policy_decisions",
          "eval_runs", "shadow_runs", "red_team_runs", "drift_events", "agent_incidents",
          "model_calls", "output_validations", "agent_costs", "ai_audits"]),
    17: (26, "vertical_solutions", "vertical_solution_factory",
         ["vertical_control_evidence", "industry_recipe_versions", "industry_eval_runs",
          "industry_safety_cases", "vertical_certifications", "vertical_conformance_reports"]),
    18: (27, "group_integration", "group_integration_factory",
         ["clean_team_access_logs", "day_one_rehearsals", "person_account_matches",
          "group_data_quality_results", "group_data_reconciliations", "integration_flow_observations",
          "standalone_validations", "synergy_acceptances", "integration_incidents",
          "business_readiness_acceptances", "legacy_retirement_evidence", "group_integration_reports"]),
}

DEFINED_TABLES = {
    17: [
        "vertical_solution_packs", "vertical_pack_versions", "industry_domain_models",
        "industry_entities", "industry_aggregates", "industry_workflows", "industry_state_machines",
        "industry_invariants", "industry_terminology", "industry_code_sets", "regulatory_controls",
        "jurisdiction_overlays", "control_crosswalks", "vertical_control_evidence",
        "industry_data_classifications", "industry_residency_rules", "industry_identity_roles",
        "industry_authorization_rules", "industry_events", "industry_api_contracts",
        "industry_recipes", "industry_recipe_versions", "industry_golden_cases", "industry_eval_cases",
        "industry_eval_runs", "industry_reference_architectures", "industry_deployment_profiles",
        "industry_slos", "industry_risks", "industry_safety_cases", "vertical_products",
        "vertical_entitlements", "vertical_prices", "vertical_poc_packs", "vertical_sow_templates",
        "vertical_partners", "vertical_certifications", "regional_vertical_launches",
        "vertical_marketplace_assets", "vertical_conformance_reports",
    ],
    18: [
        "integration_programs", "deal_theses", "integration_archetypes", "clean_team_memberships",
        "clean_team_access_logs", "day_one_services", "day_one_rehearsals", "day_hundred_outcomes",
        "imo_workstreams", "group_applications", "group_repositories", "group_databases",
        "group_interfaces", "group_dependency_edges", "duplicate_system_candidates",
        "application_dispositions", "group_business_capabilities", "group_legal_entities",
        "transition_services", "integration_risks", "target_enterprise_architectures",
        "technology_standards", "technology_exceptions", "integration_waves",
        "migration_factory_capacity", "identity_estates", "person_account_matches",
        "identity_federations", "identity_cutovers", "group_data_domains", "group_canonical_models",
        "master_data_matches", "group_data_quality_results", "group_data_migrations",
        "group_data_reconciliations", "group_integration_interfaces", "integration_flow_observations",
        "tsa_exit_plans", "carve_out_perimeters", "standalone_validations", "synergy_baselines",
        "synergy_initiatives", "one_time_costs", "stranded_costs", "synergy_acceptances",
        "integration_raid_items", "integration_incidents", "business_readiness_acceptances",
        "legacy_retirement_plans", "legacy_retirement_evidence", "group_integration_reports",
    ],
}


def parse_skills(text: str) -> list[tuple[int, str, str]]:
    matches = list(SKILL_HEADING.finditer(text))
    result: list[tuple[int, str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if index + 1 == len(matches):
            following = TOP_HEADING.search(text, match.end())
            if following:
                end = following.start()
        section = text[match.end():end].strip()
        result.append((int(match.group(1)), match.group(2).strip(), section))
    return result


def section_value(section: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$", section, re.MULTILINE)
    if not match:
        return ""
    following = re.search(r"^## ", section[match.end():], re.MULTILINE)
    end = match.end() + following.start() if following else len(section)
    return section[match.end():end].strip()


def plain_summary(value: str, fallback: str) -> str:
    lines = []
    in_fence = False
    for raw in value.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line or line.startswith("#"):
            continue
        line = re.sub(r"^[*+-]\s*", "", line)
        if line:
            lines.append(line)
    return " ".join(lines) or fallback


def table_text(value: str, fallback: str) -> str:
    text = plain_summary(value, fallback).replace("|", "\\|")
    return re.sub(r"\s+", " ", text)


def gate_for(batch: int, skill_id: int) -> str:
    if batch == 15:
        return ("C15-A" if skill_id <= 469 else "C15-B" if skill_id <= 476 else
                "C15-C" if skill_id <= 492 else "C15-D" if skill_id <= 503 else
                "C15-E" if skill_id <= 512 else "C15-G" if skill_id == 525 else "C15-F")
    if batch == 16:
        return ("AI16-A" if skill_id <= 530 else "AI16-B" if skill_id <= 543 else
                "AI16-C" if skill_id <= 558 else "AI16-D" if skill_id <= 575 else
                "AI16-E" if skill_id <= 576 else "AI16-F" if skill_id <= 591 else "AI16-G")
    if batch == 17:
        return ("V17-A" if skill_id <= 603 else "V17-C" if skill_id <= 604 else
                "V17-D" if skill_id <= 605 else "V17-E" if skill_id <= 661 else
                "V17-F" if skill_id <= 667 else "V17-G")
    return ("M18-A" if skill_id <= 673 else "M18-B" if skill_id <= 682 else
            "M18-C" if skill_id <= 690 else "M18-D" if skill_id <= 711 else
            "M18-E" if skill_id <= 724 else "M18-F" if skill_id <= 728 else
            "M18-G" if skill_id <= 734 else "M18-H")


def reference_body(batch: Batch) -> str:
    specific = {
        15: "Do not execute banking, payments, hiring, termination, compensation, equity, fundraising, legal, board, policy-waiver, or crisis actions.",
        16: "Do not invoke live tools, provision credentials, modify Agent authority, promote autonomy, make high-impact human decisions, or claim unbounded autonomy.",
        17: "Do not claim regulatory compliance, professional approval, partner certification, production safety, industry acceptance, or cross-region applicability.",
        18: "Do not access clean-team data, merge identities or data, switch production systems, exit a TSA, retire assets, or recognize financial synergy.",
    }[batch.number]
    return f"""# Batch {batch.number} evidence boundary

Use this boundary for every authoritative Skill {batch.first}–{batch.last} in the {batch.title}.

## Model and final gate

- Model: `{batch.model}`.
- Final gate: `{batch.final_gate}`.
- Authority text status: `{batch.final_status}` only after complete external evidence.
- Repository artifacts, generated plans, schemas, simulations, unit tests, and local database tests never close a field gate by themselves.

## Mandatory operating boundary

1. Bind every decision to tenant/company, legal entity, region, jurisdiction, fiscal or program period, version, owner, authority, confidentiality, and evidence window.
2. Preserve `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, and `BLOCKED` without translating absence into success.
3. Require immutable evidence references, source authority, freshness, approvals, conflicts, costs, risks, stop conditions, and responsible human owners.
4. Keep every gate sequential and non-compensating. Revenue, speed, automation, partner demand, transaction close, or local tests cannot offset a failed safety, legal, financial, privacy, security, human-accountability, or evidence gate.
5. {specific}
6. Record `external_operation_executed=false` for control-plane-only work. If a required external authority is unavailable, return `NOT_RUN` or `BLOCKED`.

## Required result

Return a version-bound decision containing the highest satisfied gate, blockers, non-blocking items, negative results, evidence references, approval state, open risks, restrictions, and `external_operation_executed=false`.
"""


def skill_body(batch: Batch, skill_id: int, name: str, authority: str) -> str:
    description_value = plain_summary(section_value(authority, "Description"), name.replace("-", " "))
    description = (
        f"Execute authoritative Batch {batch.number} Skill {skill_id} for {description_value}. "
        f"Use when Codex must design, operate, review, or verify this {batch.title} capability."
    )
    heading = " ".join(part.capitalize() for part in name.split("-"))
    return f"""---
name: {name}
description: {json.dumps(description, ensure_ascii=False)}
---

# {heading}

## Operating contract

Apply authoritative Batch {batch.number} Skill {skill_id}. Read [the shared Batch {batch.number} evidence boundary](../references/{batch.reference}) before acting.

1. Pin tenant/company, legal entity, region, jurisdiction, period, source version, policy version, owner, approval authority, confidentiality, and evidence window.
2. Confirm systems of record and required inputs. Treat missing, stale, conflicting, unauthorized, or cross-boundary evidence as `NOT_RUN`, `INCONCLUSIVE`, or blocking.
3. Execute or evaluate the capability using the authoritative specification below; keep safety, security, privacy, legal, financial, human-accountability, quality, and evidence gates non-compensating.
4. Preserve failed, negative, delayed, and partially observed outcomes. Do not convert plans, generated artifacts, simulations, repository tests, or fluent model output into field success.
5. Record assumptions, costs, risks, decisions, approvals, evidence references, stop conditions, and the responsible human owner.
6. Return acceptance as `PASSED`, `FAILED`, `NOT_RUN`, `INCONCLUSIVE`, `NOT_APPLICABLE`, or `BLOCKED`; do not claim `{batch.final_gate}` from local implementation evidence.

## Authoritative specification

{authority}

## Required result

Return a version-bound, evidence-linked decision with blockers, non-blocking items, open risks, approval state, and `external_operation_executed=false` for control-plane-only evaluation.
"""


def schema_header(batch: Batch, name: str) -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://schemas.elmos.io/company-series/batch-{batch.number}/{name}.schema.json",
        "title": f"Batch {batch.number} {name.replace('-', ' ').title()}",
        "type": "object",
    }


def generate_schemas(batch: Batch, repo: Path) -> None:
    group = repo / "contracts" / SCHEMA_GROUPS[batch.number]
    group.mkdir(parents=True, exist_ok=True)
    common_required = ["batch", "program_id", "source_version", "organization_id"]
    program = schema_header(batch, "program")
    program.update({
        "additionalProperties": False,
        "required": common_required + ["model", "owner_id", "dimensions", "observed_at", "evidence_refs"],
        "properties": {
            "batch": {"const": batch.number},
            "model": {"const": batch.model},
            "program_id": {"type": "string", "minLength": 1},
            "source_version": {"type": "string", "minLength": 1},
            "organization_id": {"type": "string", "minLength": 1},
            "owner_id": {"type": "string", "minLength": 1},
            "dimensions": {"type": "array", "items": {"enum": DIMENSIONS[batch.number]},
                           "minItems": len(DIMENSIONS[batch.number]), "uniqueItems": True},
            "observed_at": {"type": "string", "format": "date-time"},
            "evidence_refs": {"type": "array", "items": {"type": "string", "minLength": 1},
                              "minItems": 1, "uniqueItems": True},
            "external_operation_executed": {"const": False},
        },
    })
    program["required"].append("external_operation_executed")

    evidence = schema_header(batch, "gate-evidence")
    evidence.update({
        "additionalProperties": False,
        "required": common_required + ["gate", "status", "coverage", "tenant_boundary_passed",
                                         "legal_and_policy_passed", "human_accountability_passed",
                                         "critical_open_risks", "authority_id", "observed_at",
                                         "evidence_refs", "external_operation_executed"],
        "properties": {
            "batch": {"const": batch.number},
            "program_id": {"type": "string", "minLength": 1},
            "source_version": {"type": "string", "minLength": 1},
            "organization_id": {"type": "string", "minLength": 1},
            "gate": {"enum": GATES[batch.number]},
            "status": {"enum": ["PASSED", "FAILED", "NOT_RUN", "INCONCLUSIVE", "NOT_APPLICABLE", "BLOCKED"]},
            "coverage": {"type": "number", "minimum": 0, "maximum": 1},
            "tenant_boundary_passed": {"type": "boolean"},
            "legal_and_policy_passed": {"type": "boolean"},
            "human_accountability_passed": {"type": "boolean"},
            "critical_open_risks": {"type": "integer", "minimum": 0},
            "authority_id": {"type": "string", "minLength": 1},
            "observed_at": {"type": "string", "format": "date-time"},
            "evidence_refs": {"type": "array", "items": {"type": "string", "minLength": 1},
                              "minItems": 1, "uniqueItems": True},
            "external_operation_executed": {"const": False},
        },
    })

    pack = schema_header(batch, "evidence-pack")
    pack.update({
        "additionalProperties": False,
        "required": ["batch", "program_id", "source_version", "organization_id", "gate_evidence",
                     "complete", "external_operation_executed"],
        "properties": {
            "batch": {"const": batch.number},
            "program_id": {"type": "string", "minLength": 1},
            "source_version": {"type": "string", "minLength": 1},
            "organization_id": {"type": "string", "minLength": 1},
            "gate_evidence": {"type": "array", "items": {"$ref": "gate-evidence.schema.json"},
                              "minItems": len(GATES[batch.number]), "maxItems": len(GATES[batch.number])},
            "complete": {"type": "boolean"},
            "external_operation_executed": {"const": False},
        },
    })

    report = schema_header(batch, "conformance-report")
    report.update({
        "additionalProperties": False,
        "required": ["batch", "model", "program_id", "source_version", "organization_id", "gate",
                     "status", "ready", "evidence_complete", "supported_dimensions", "blockers",
                     "restrictions", "evaluated_at", "evidence_refs", "external_operation_executed"],
        "properties": {
            "batch": {"const": batch.number},
            "model": {"const": batch.model},
            "program_id": {"type": "string", "minLength": 1},
            "source_version": {"type": "string", "minLength": 1},
            "organization_id": {"type": "string", "minLength": 1},
            "gate": {"enum": ["BLOCKED"] + GATES[batch.number]},
            "status": {"enum": ["BLOCKED", "PARTIAL", batch.final_status]},
            "ready": {"type": "boolean"},
            "evidence_complete": {"type": "boolean"},
            "supported_dimensions": {"type": "array", "items": {"enum": DIMENSIONS[batch.number]},
                                     "uniqueItems": True},
            "blockers": {"type": "array", "items": {"type": "string"}},
            "restrictions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "evaluated_at": {"type": "string", "format": "date-time"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
            "external_operation_executed": {"const": False},
        },
        "allOf": [{
            "if": {"properties": {"ready": {"const": True}}, "required": ["ready"]},
            "then": {"properties": {
                "gate": {"const": batch.final_gate},
                "status": {"const": batch.final_status},
                "evidence_complete": {"const": True},
                "blockers": {"maxItems": 0},
            }},
        }],
    })

    for name, schema in (("program", program), ("gate-evidence", evidence),
                         ("evidence-pack", pack), ("conformance-report", report)):
        (group / f"{name}.schema.json").write_text(
            json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def authority_database_tables(batch: Batch, raw: str) -> list[str]:
    if batch.number in DEFINED_TABLES:
        return DEFINED_TABLES[batch.number]
    marker = f"Batch {batch.number}核心数据库建议"
    start = raw.index(marker)
    fence_start = raw.index("```text", start) + len("```text")
    fence_end = raw.index("```", fence_start)
    tables = [line.strip() for line in raw[fence_start:fence_end].splitlines() if line.strip()]
    if not tables or any(not re.fullmatch(r"[a-z][a-z0-9_]*", value) for value in tables):
        raise SystemExit(f"Batch {batch.number} database table block is invalid")
    return tables


def generate_migration(batch: Batch, raw: str, repo: Path) -> str:
    version, schema_name, slug, append_only = PERSISTENCE[batch.number]
    tables = authority_database_tables(batch, raw)
    unknown = sorted(set(append_only) - set(tables))
    if unknown:
        raise SystemExit(f"Batch {batch.number} append-only tables are absent: {unknown}")
    quoted_tables = ",\n        ".join(f"'{value}'" for value in tables)
    quoted_append = ",\n        ".join(f"'{value}'" for value in append_only)
    sql = f"""-- ELMOS authoritative company-series Batch {batch.number}: {batch.title}.
-- The dedicated schema preserves canonical logical names without colliding with earlier technical batches.
-- This migration stores tenant-scoped observations and decisions; it executes no external business action.

CREATE SCHEMA IF NOT EXISTS {schema_name};

DO $$
DECLARE
    target_schema text := '{schema_name}';
    table_name text;
    batch_tables text[] := ARRAY[
        {quoted_tables}
    ];
    append_only_tables text[] := ARRAY[
        {quoted_append}
    ];
BEGIN
    FOREACH table_name IN ARRAY batch_tables LOOP
        EXECUTE format(
            'CREATE TABLE %I.%I (' ||
            'record_id varchar(96) PRIMARY KEY,' ||
            'organization_id varchar(96) NOT NULL REFERENCES public.organizations(organization_id),' ||
            'company_id varchar(96) NOT NULL,' ||
            'tenant_id varchar(96) NOT NULL,' ||
            'program_id varchar(160) NOT NULL,' ||
            'legal_entity_id varchar(160),' ||
            'region varchar(64),' ||
            'jurisdiction varchar(64),' ||
            'fiscal_period varchar(32),' ||
            'wave_id varchar(160),' ||
            'owner_id varchar(160) NOT NULL,' ||
            'human_owner_id varchar(160) NOT NULL,' ||
            'status varchar(64) NOT NULL DEFAULT ''OBSERVED'',' ||
            'version varchar(64) NOT NULL,' ||
            'approved_by varchar(160),' ||
            'confidentiality varchar(64) NOT NULL DEFAULT ''CONFIDENTIAL'',' ||
            'source varchar(160) NOT NULL,' ||
            'source_record_ref varchar(512) NOT NULL,' ||
            'idempotency_key varchar(160) NOT NULL,' ||
            'evidence_refs jsonb NOT NULL DEFAULT ''[]''::jsonb,' ||
            'content_hash varchar(64) CHECK (content_hash IS NULL OR content_hash ~ ''^[0-9a-f]{{64}}$''),' ||
            'payload jsonb NOT NULL DEFAULT ''{{}}''::jsonb,' ||
            'external_operation_executed boolean NOT NULL DEFAULT false CHECK (external_operation_executed = false),' ||
            'observed_at timestamptz NOT NULL,' ||
            'created_at timestamptz NOT NULL DEFAULT now(),' ||
            'updated_at timestamptz NOT NULL DEFAULT now(),' ||
            'UNIQUE (organization_id, idempotency_key),' ||
            'UNIQUE (organization_id, source, source_record_ref, version))',
            target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id)',
                       'idx_' || table_name || '_organization', target_schema, table_name);
        EXECUTE format('CREATE INDEX %I ON %I.%I (organization_id, program_id, status)',
                       'idx_' || table_name || '_program', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format('ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY', target_schema, table_name);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I.%I USING (organization_id = current_setting(''app.organization_id'', true)) WITH CHECK (organization_id = current_setting(''app.organization_id'', true))',
            target_schema, table_name);
        IF table_name = ANY(append_only_tables) THEN
            EXECUTE format(
                'CREATE TRIGGER company_series_append_only BEFORE UPDATE OR DELETE ON %I.%I FOR EACH ROW EXECUTE FUNCTION public.elmos_forbid_append_only_mutation()',
                target_schema, table_name);
        END IF;
    END LOOP;
END;
$$;
"""
    filename = f"V{version}__{slug}.sql"
    output = repo / "modules" / "persistence" / "src" / "main" / "resources" / "db" / "migration" / filename
    output.write_text(sql, encoding="utf-8")
    return f"modules/persistence/src/main/resources/db/migration/{filename}"


def generate(batch: Batch, spec_file: Path, repo: Path) -> None:
    raw = spec_file.read_text(encoding="utf-8")
    skills = parse_skills(raw)
    ids = [skill_id for skill_id, _, _ in skills]
    expected = list(range(batch.first, batch.last + 1))
    if ids != expected:
        raise SystemExit(f"Batch {batch.number} IDs are not exact: {ids[:3]}...{ids[-3:]}")

    group = repo / "agent-skills" / batch.group
    references = group / "references"
    references.mkdir(parents=True, exist_ok=True)
    (references / batch.reference).write_text(reference_body(batch), encoding="utf-8")

    checklist = [
        f"# Batch {batch.number} {batch.title} acceptance checklist",
        "",
        "Repository implementation does not close field acceptance. Every row remains `NOT_RUN` until the named external system of record supplies current, authorized, version-bound evidence.",
        "",
        "| Skill | Gate | Capability | Authoritative acceptance | Field status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for skill_id, name, authority in skills:
        skill_dir = group / name
        if not (skill_dir / "agents" / "openai.yaml").is_file():
            raise SystemExit(f"Skill {skill_id} was not initialized: {skill_dir}")
        (skill_dir / "SKILL.md").write_text(
            skill_body(batch, skill_id, name, authority), encoding="utf-8")
        capability = table_text(section_value(authority, "Description"), name.replace("-", " "))
        acceptance = section_value(authority, "Acceptance Criteria")
        if not acceptance:
            acceptance = section_value(authority, "Hard Rules")
        checklist.append(
            f"| {skill_id} `{name}` | {gate_for(batch.number, skill_id)} | "
            f"{capability} | {table_text(acceptance, 'Authoritative hard rules apply.')} | `NOT_RUN` |")

    (repo / "docs" / batch.checklist).write_text("\n".join(checklist) + "\n", encoding="utf-8")
    generate_schemas(batch, repo)
    migration = generate_migration(batch, raw, repo)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    manifest = {
        "batch": batch.number,
        "skill_range": [batch.first, batch.last],
        "skill_count": len(skills),
        "source_file": spec_file.name,
        "source_sha256": digest,
        "generated_groups": [f"agent-skills/{batch.group}", f"docs/{batch.checklist}",
                             f"contracts/{SCHEMA_GROUPS[batch.number]}", migration],
        "external_operation_executed": False,
    }
    (repo / "docs" / f"batch-{batch.number}-company-series-source-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    for number in BATCHES:
        parser.add_argument(f"--batch-{number}", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    for number, batch in BATCHES.items():
        generate(batch, getattr(args, f"batch_{number}"), repo)


if __name__ == "__main__":
    main()
