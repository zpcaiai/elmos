---
name: chinadb-61-fixture-corpus-and-mutation-tests
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Commercial Fixture Corpus & Mutation Tests. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "61-fixture-corpus-and-mutation-tests"
  source_path: "skills/61-fixture-corpus-and-mutation-tests/SKILL.md"
  source_sha256: "sha256:ae53be02649600da79b300d1a8cf034362fcc8e488f3008c576151b4ac29fa33"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
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

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `61-fixture-corpus-and-mutation-tests`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
