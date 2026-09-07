---
name: chinadb-13-production-migration-certification
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for E1-E5 Production Migration Certification. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "13-production-migration-certification"
  source_path: "skills/13-production-migration-certification/SKILL.md"
  source_sha256: "sha256:57714b82eb19a8c4ea857761316b9109176eeca547c07216aac8cd8cc144aa10"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# E1-E5 Production Migration Certification

- **Skill ID:** `13-production-migration-certification`
- **Version:** `1.0.0`
- **Category:** core/certification
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Issue a reproducible, evidence-backed migration decision across static conversion, data integrity, behavior, performance and operational readiness. Certification is release-candidate and route-fingerprint specific.

## Inputs

- All evidence index
- Default/route-specific gate policy
- Waivers and approvals
- Release candidate hash
- Route fingerprint

## Required outputs

- Certification JSON
- Human-readable certificate
- Blocking findings
- Expiry/recertification triggers

## Implementation modules / repository contract

- certify/gates.py
- certify/policy.py
- certify/waivers.py
- certify/report.py
- certify/fingerprint.py

## Interfaces and contracts

- Gate defaults in config/default-gates.yaml
- Any route-affecting change invalidates affected gates

## Workflow

1. Verify evidence authenticity/fingerprints and freshness.
2. Evaluate E1 static/compile conversion.
3. Evaluate E2 data integrity and CDC reconciliation.
4. Evaluate E3 behavior and transaction equivalence.
5. Evaluate E4 performance/SLO equivalence.
6. Evaluate E5 security/operations/rehearsal/rollback readiness.
7. Apply only explicit non-expired waivers with owner and compensating controls.
8. Issue certified/rejected/conditional decision tied to exact RC.

## Mandatory tests

- Missing evidence
- Stale benchmark after schema change
- Waiver expiry
- Changed target version/config
- Changed app build after E3
- Tampered evidence hash

## Required evidence

- `schemas/certification.schema.json` instance
- Certificate markdown
- Gate calculation trace
- Waiver ledger

## Fail-closed / escalation rules

- No certification based on vendor migration-tool success alone.
- P0/P1 behavior mismatch cannot be waived by an automated agent.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `13-production-migration-certification`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
