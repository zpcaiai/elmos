# Release CI & Quality Gates

- **Skill ID:** `16-release-ci-quality-gates`
- **Version:** `1.0.0`
- **Category:** core/release
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Continuously test parsers, IR, rules, adapters and migration routes using golden corpora, ephemeral databases and regression suites; prevent rule changes from silently breaking previously certified semantics.

## Inputs

- Skill/package version
- Rule packs
- Fixture corpora
- Supported engine/version matrix
- Container/ephemeral DB definitions

## Required outputs

- CI pipelines
- Golden corpus report
- Adapter compatibility matrix
- Regression trend
- Release artifact checksums

## Implementation modules / repository contract

- ci/route_matrix.py
- ci/fixtures.py
- ci/ephemeral.py
- ci/regression.py
- ci/release.py

## Workflow

1. Run fast parser/IR/rule unit tests on every change.
2. Run target-adapter compile tests against supported versions.
3. Run representative cross-engine differential suites on merge/release.
4. Run performance smoke tests and scheduled full benchmarks.
5. Fail CI on uncovered high-risk rule, stale golden output or undocumented capability change.
6. Publish versioned route-support matrix and evidence hashes.

## Mandatory tests

- Backward compatibility of IR
- Rule conflict
- Target minor-version drift
- Golden result drift
- Schema validator failures

## Required evidence

- CI logs
- Route test matrix
- Coverage report
- Release checksum manifest

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
