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
