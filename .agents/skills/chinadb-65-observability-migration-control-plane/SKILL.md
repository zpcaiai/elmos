---
name: chinadb-65-observability-migration-control-plane
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Migration Observability & Control Plane. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "65-observability-migration-control-plane"
  source_path: "skills/65-observability-migration-control-plane/SKILL.md"
  source_sha256: "sha256:6344bf1f80bcd3ac073d9493a4c89c70f6379dbef8b866e03e746d935791e2a8"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Migration Observability & Control Plane

- **Skill ID:** `65-observability-migration-control-plane`
- **Version:** `1.0.0`
- **Category:** operations
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Expose route state, object conversion progress, copy/CDC lag, mismatch rates, repair queues, gate status and cutover readiness for enterprise operators.

## Inputs

- Orchestrator events
- Evidence ledger
- Data movement metrics
- Verification/performance metrics

## Required outputs

- Operator API
- Dashboards/status views
- Alerts
- Audit timeline
- Readiness summary

## Implementation modules / repository contract

- control/api.py
- control/events.py
- control/metrics.py
- control/alerts.py
- control/readiness.py

## Workflow

1. Expose per-route immutable run id and current stage.
2. Show full-load/CDC positions and gap alerts.
3. Show unsupported/high-risk object queue and repair approvals.
4. Show E1-E5 gate status with links to evidence.
5. Alert on stalled CDC, checksum mismatch, performance regression, expired waiver and cutover blockers.

## Mandatory tests

- Event replay
- Metrics cardinality
- Access control
- Stale evidence alert
- Multi-tenant isolation

## Required evidence

- API contract tests
- Dashboard data fixtures
- Alert firing tests
- Audit logs

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `65-observability-migration-control-plane`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
