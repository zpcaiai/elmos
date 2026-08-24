---
name: chinadb-64-vendor-native-tool-bridge
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Vendor-Native Migration Tool Bridge. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "64-vendor-native-tool-bridge"
  source_path: "skills/64-vendor-native-tool-bridge/SKILL.md"
  source_sha256: "sha256:58df66f1e8315a394c30d6abc0be124f97071ce634be79c4a8fd00cca05d9f6a"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Vendor-Native Migration Tool Bridge

- **Skill ID:** `64-vendor-native-tool-bridge`
- **Version:** `1.0.0`
- **Category:** integration
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Wrap vendor-native migration/assessment tools as optional providers while normalizing their outputs into the platform evidence model and avoiding vendor lock-in in the core architecture.

## Inputs

- Tool availability/license/API/CLI
- Route manifest
- Vendor tool config

## Required outputs

- Provider capabilities
- Normalized progress/events
- Imported assessment/conversion findings
- Evidence links
- Fallback path

## Implementation modules / repository contract

- vendor_tools/base.py
- vendor_tools/dm.py
- vendor_tools/kingbase.py
- vendor_tools/opengauss.py
- vendor_tools/gbase.py
- vendor_tools/highgo.py
- vendor_tools/oceanbase.py
- vendor_tools/gaussdb.py
- vendor_tools/goldendb.py

## Workflow

1. Discover tool version/capability safely.
2. Generate config without embedded secrets.
3. Run/import status through adapter-specific provider.
4. Normalize findings without treating vendor success as E3/E4/E5 proof.
5. Fall back to generic engine where supported.

## Mandatory tests

- Tool missing
- License unavailable
- Partial failure
- Resume/retry
- Vendor output schema change

## Required evidence

- Vendor tool version
- Normalized evidence
- Raw-log reference/redacted hash

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `64-vendor-native-tool-bridge`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
