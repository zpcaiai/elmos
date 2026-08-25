# Guarded Automatic Repair

- **Skill ID:** `11-guarded-auto-repair`
- **Version:** `1.0.0`
- **Category:** core/repair
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Turn compilation, behavior and performance failures into bounded SQL/DDL/procedural/application/config/test patches, then verify each patch through the relevant gates. High-risk or semantic-degrading repairs require approval.

## Inputs

- Failed evidence/minimal reproduction
- Rule/mutation catalog
- Source/target IR
- Application repo
- Risk policy

## Required outputs

- Ranked repair candidates
- Patch set
- Repair rationale/risk
- Verification plan/results
- Promoted rule or rejected candidate

## Implementation modules / repository contract

- repair/classify.py
- repair/generate.py
- repair/patch.py
- repair/rank.py
- repair/verify.py
- repair/promote_rule.py

## Interfaces and contracts

- Uses `schemas/repair-plan.schema.json`
- Never writes production state directly

## Workflow

1. Classify failure root cause before generating a patch.
2. Generate the smallest reversible change with source mapping.
3. Score semantic risk, blast radius and maintainability.
4. Require approval for high/critical risk or emulation.
5. Run compile + targeted E2/E3/E4 tests as applicable.
6. Reject patches that fix one fixture but regress golden corpus.
7. Promote repeated safe fixes into versioned rules with tests.

## Mandatory tests

- Conflicting repairs
- Patch that changes transaction scope
- Index/tuning patch with write regression
- Precision widening/narrowing
- App-lift repair
- Retry-policy repair
- Dynamic SQL injection regression

## Required evidence

- Repair plan schema instance
- Git diff/patch hash
- Before/after evidence
- Approval record if needed
- Rule-promotion test

## Fail-closed / escalation rules

- No repair is accepted solely because target SQL compiles.
- High-risk patches cannot self-approve.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
