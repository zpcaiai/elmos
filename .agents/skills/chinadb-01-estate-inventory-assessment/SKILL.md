---
name: chinadb-01-estate-inventory-assessment
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Estate Inventory & Migration Assessment. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "01-estate-inventory-assessment"
  source_path: "skills/01-estate-inventory-assessment/SKILL.md"
  source_sha256: "sha256:aa6508b5bc5552f4956e6b8c9e81a0d7806eb9e552ed1e86d66ab26f97e411f9"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Estate Inventory & Migration Assessment

- **Skill ID:** `01-estate-inventory-assessment`
- **Version:** `1.0.0`
- **Category:** core/assessment
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Inventory database objects, data volume, workload dependencies and application SQL usage, then produce a quantified compatibility/risk/effort assessment before any migration coding.

## Inputs

- Source DB metadata/catalog access
- SQL/workload samples or captured traces
- Application repositories
- Target adapter capability catalog
- Business criticality annotations

## Required outputs

- Object inventory with dependency graph
- Dialect/feature usage histogram
- Data-volume/LOB/partition profile
- Application SQL and stored-logic call graph
- Unsupported/risky construct list
- Effort estimate by auto/assisted/manual bands

## Implementation modules / repository contract

- assessment/catalog_scan.py
- assessment/sql_inventory.py
- assessment/app_sql_scan.py
- assessment/dependency_graph.py
- assessment/risk_model.py

## Interfaces and contracts

- Every finding has stable `finding_id`, source span, severity, suggested strategy
- Output feeds Semantic IR and route planner

## Workflow

1. Fingerprint source version/NLS/collation/timezone/compatibility settings.
2. Extract all schema/security/procedural objects with dependencies.
3. Scan app code for literal/native SQL, stored procedure calls, driver APIs and DB-specific error handling.
4. Sample/capture workload and classify critical transaction paths.
5. Evaluate every construct against target adapter capability matrix.
6. Produce migration scorecard with route blockers and evidence-backed work estimate.

## Mandatory tests

- Quoted/mixed-case identifiers
- Dynamic SQL invisible to static scans
- Synonyms and cross-schema dependencies
- DB links / linked servers
- LOB-heavy tables
- Generated/identity columns
- External jobs/files/CLR/Java stored code
- Application SQL constructed across multiple strings

## Required evidence

- Inventory JSON
- Dependency graph snapshot
- Compatibility findings with source spans
- Assessment report using template
- Coverage metric: discovered objects vs catalog totals

## Fail-closed / escalation rules

- If catalog permissions are incomplete, assessment must be marked incomplete.
- Unknown dynamic SQL is a risk item, not assumed compatible.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `01-estate-inventory-assessment`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
