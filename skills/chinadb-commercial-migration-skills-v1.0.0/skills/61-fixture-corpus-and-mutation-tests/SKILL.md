# Commercial Fixture Corpus & Mutation Tests

- **Skill ID:** `61-fixture-corpus-and-mutation-tests`
- **Version:** `1.0.0`
- **Category:** quality
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Build a large reusable corpus of real-world DDL/SQL/PL/T-SQL/application patterns plus semantic mutations that prove the verifier catches incorrect conversions instead of merely accepting generated code.

## Inputs

- Public/synthetic SQL patterns
- De-identified customer-derived cases where permitted
- Known vendor incompatibilities
- Production bug reproductions

## Required outputs

- Golden fixture corpus
- Negative/mutation corpus
- Expected semantics metadata
- Coverage dashboard

## Implementation modules / repository contract

- fixtures/catalog.py
- fixtures/generator.py
- fixtures/mutations.py
- fixtures/expected.py

## Workflow

1. Create minimal fixtures by feature and cross-feature interactions.
2. Add boundary values for types/time/null/collation.
3. Generate intentionally wrong conversions: dropped predicate, changed rounding, lost rollback, wrong ordering, trigger omission, key-generation bug.
4. Require verification engine to detect mutations.
5. Tag fixtures by source/target/version and risk.

## Mandatory tests

- Verifier mutation score
- Cross-feature interaction fixtures
- Concurrency fixtures
- Large object and unicode fixtures

## Required evidence

- Fixture manifest/hash
- Mutation score
- Coverage by rule/object/risk

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
