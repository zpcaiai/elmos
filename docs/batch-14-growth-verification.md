# Batch 14 growth and ecosystem verification

Repository verification date: 2026-07-21.

This record covers the authoritative cross-language product-growth Batch 14. It proves local PEGM control-plane behavior, Skill packaging, schemas, artifact contracts and V22 persistence boundaries only. External product, content, developer, community, Marketplace, localization, compliance, partner, economics and regional field evidence remains `NOT_RUN`.

## Verification matrix

| Area | Local result | Field boundary |
| --- | --- | --- |
| PEGM evaluator | G14-A through G14-G are sequential and non-compensating across six assurance areas | No external authority was contacted |
| Admission | Signed immutable B13-G artifact, Monthly Verified Migration Value, seven domains and five flywheels required | No real platform was admitted |
| Fail-closed behavior | Missing control/evidence, mismatch, future time, privacy, tenant, guardrail, fabricated result, unauthorized action, invisible economics and open risk block | No provider status was inferred |
| Artifacts | Exact `growth-platform/` tree, 25 immutable files, 12 specified reports and Zstandard profile streams | No report establishes a field outcome |
| Path safety | Existing target, workspace symlink and direct/resolved repository path rejected | No customer repository was written |
| Skills | Exactly 60 authoritative Skill 401–460 packages passed Skill Creator validation | No Skill performed or proved an external operation |
| Schemas | 18 strict Draft 2020-12 schemas parse and local references resolve | Schema validity is not operational acceptance |
| Persistence | V22 creates the exact 69 proposed tables, forced RLS and 18 append-only streams | V10/external systems retain execution authority |

## Commands

```bash
JAVA_HOME=/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home \
  /opt/homebrew/Cellar/maven/3.9.10/bin/mvn -pl modules/ecosystem-growth test

JAVA_HOME=/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home \
  /opt/homebrew/Cellar/maven/3.9.10/bin/mvn -pl modules/architecture-tests \
  -Dtest=BatchFourteenGrowthAssuranceTest test

JAVA_HOME=/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home \
  /opt/homebrew/Cellar/maven/3.9.10/bin/mvn -pl modules/persistence \
  -Dtest=TenantMigrationContractTest test

for skill in agent-skills/ecosystem-growth/*/SKILL.md; do
  python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py "$(dirname "$skill")"
done

for schema in contracts/ecosystem-growth-schema/*.schema.json; do
  jq empty "$schema"
done

JAVA_HOME=/opt/homebrew/Cellar/openjdk@21/21.0.11/libexec/openjdk.jdk/Contents/Home \
  /opt/homebrew/Cellar/maven/3.9.10/bin/mvn test
```

## Recorded result

- Focused PEGM module: 9 tests, zero failures, errors or skips.
- Batch 14 architecture assurance: 4 tests, zero failures, errors or skips.
- Persistence migration contract: 1 test, zero failures, errors or skips.
- Skill Creator validation: all 60 authoritative Skills valid.
- Contracts: all 18 JSON Schemas parse and every local reference resolves.
- PostgreSQL 17.5 V1–V22: 1,286 public tables, 1,285 forced-RLS tables and 1,285 `tenant_isolation` policies.
- V22: all 69 authoritative Batch 14 tables and all 18 append-only triggers exist.
- RLS probe: a non-owner role scoped to `org-growth-a` saw exactly one of two tenant rows.
- Append-only probe: update of `growth_events` was blocked.
- Full 53-module Maven reactor: exit code 0 after the parallel Batch 21 baselines converged.

The current parallel V23 migration was not changed by this Batch 14 work. The green Maven reactor does not execute a complete PostgreSQL V1–V23 load: a separate diagnostic reaches V23 and then V23 fails because `business_capabilities` already exists. V1–V22, including the reconciled V22, applies successfully.
