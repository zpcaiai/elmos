---
name: chinadb-60-route-support-matrix
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Route Support Matrix & Compatibility Governance. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "60-route-support-matrix"
  source_path: "skills/60-route-support-matrix/SKILL.md"
  source_sha256: "sha256:59a9a0bcf72a285e03358dcbf72d155937c4b0afe978d86bc9f274a805c1b1ab"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
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

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `60-route-support-matrix`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
