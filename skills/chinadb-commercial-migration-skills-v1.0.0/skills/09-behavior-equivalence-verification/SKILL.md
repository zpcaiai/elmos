# Behavioral Equivalence Verification

- **Skill ID:** `09-behavior-equivalence-verification`
- **Version:** `1.0.0`
- **Category:** core/verification
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Prove that source and target produce equivalent observable behavior for critical workloads: values, ordering contracts, errors, transactions, concurrency outcomes, side effects and application-visible state.

## Inputs

- Source and target test endpoints
- Scenario DSL/tests
- Converted app builds
- Masking policy for production-derived fixtures
- Equivalence comparators

## Required outputs

- Differential test report
- Mismatch clusters
- Minimal reproductions
- Transaction/concurrency evidence
- E3 gate result

## Implementation modules / repository contract

- verify/scenario.py
- verify/runner.py
- verify/compare_values.py
- verify/compare_errors.py
- verify/transactions.py
- verify/concurrency.py
- verify/side_effects.py
- verify/minimize.py

## Interfaces and contracts

- Comparator policies are explicit and versioned
- Outputs feed auto-repair and certification

## Workflow

1. Execute the same scenario against isolated source and target environments.
2. Normalize only representation differences allowed by route contract.
3. Compare scalar/rowset/LOB/time values and declared ordering semantics.
4. Compare expected errors and domain exception mapping.
5. Compare commit/rollback/savepoint/isolation/deadlock/serialization behavior.
6. Compare trigger/event/job side effects and externally visible application outcomes.
7. Minimize mismatches into stable fixtures for the repair loop.

## Mandatory tests

- Concurrent write conflicts
- Phantoms/non-repeatable reads
- Deadlock victims
- Duplicate key/FK/check errors
- NULL/empty string
- float/decimal boundaries
- timezone/DST
- unordered rowsets
- trigger side effects
- sequence gaps
- rollback after partial work

## Required evidence

- Scenario run ids
- Source/target outputs and fingerprints
- Mismatch reproductions
- E3 metrics and decision

## Fail-closed / escalation rules

- No masking/normalization may hide a business-significant difference.
- A passed happy path cannot override failed critical concurrency/error cases.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
