---
name: chinadb-16-release-ci-quality-gates
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Release CI & Quality Gates. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "16-release-ci-quality-gates"
  source_path: "skills/16-release-ci-quality-gates/SKILL.md"
  source_sha256: "sha256:b384333568afae69f0b4ddba2b4604b2ade96cc6c5f3feeb3044923f7715d6aa"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
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

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `16-release-ci-quality-gates`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
