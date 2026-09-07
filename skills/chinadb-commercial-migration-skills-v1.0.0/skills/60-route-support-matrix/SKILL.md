# Route Support Matrix & Compatibility Governance

- **Skill ID:** `60-route-support-matrix`
- **Version:** `1.0.0`
- **Category:** commercial
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Maintain a truthful, evidence-derived matrix of source->target route maturity, versions, modes, supported object classes and certification level. Prevent sales/product claims from outrunning tested capability.

## Inputs

- Adapter capability snapshots
- CI route evidence
- Released rule packs
- Known issues/waivers

## Required outputs

- Machine-readable support matrix
- Human-readable product matrix
- Route maturity: experimental/beta/production-certified
- Known limitation inventory

## Implementation modules / repository contract

- product/routes.py
- product/maturity.py
- product/limitations.py

## Workflow

1. Aggregate evidence by exact route/version/mode.
2. Compute supported object/feature classes from test evidence, not marketing labels.
3. Publish known limitations and certification expiry.
4. Downgrade maturity automatically when a target version changes without revalidation.

## Mandatory tests

- Target minor/major version change
- Expired certification
- Rule regression
- Unsupported feature added to source workload

## Required evidence

- Published matrix
- Evidence links per production-certified route
- Change log

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
