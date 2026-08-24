# Commercial Assessment, Estimation & Delivery Report

- **Skill ID:** `63-migration-estimation-commercial-report`
- **Version:** `1.0.0`
- **Category:** commercial
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Turn technical inventory into a defensible delivery estimate and migration statement of work: automation rate, manual work bands, environment needs, risk, cutover strategy and evidence deliverables.

## Inputs

- Assessment findings
- Route maturity matrix
- Object/app complexity
- Data size/change rate
- SLO/RPO/RTO

## Required outputs

- Effort bands
- Automation coverage estimate
- Environment/licensing prerequisites
- Risk register
- Proposed milestones and acceptance gates

## Implementation modules / repository contract

- reporting/estimate.py
- reporting/assessment_report.py
- reporting/risk.py

## Workflow

1. Quantify by object/query/call-site complexity rather than raw database size alone.
2. Separate data movement effort from semantic/application modernization.
3. Price high-risk/manual areas transparently.
4. Tie milestones to E1-E5 evidence.

## Mandatory tests

- Low data volume/high PL complexity
- Huge data/simple schema
- Dynamic SQL-heavy app
- TiDB lift-to-app route
- MPP analytical redesign

## Required evidence

- Assessment report
- Estimate inputs and formula version
- Risk register

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
