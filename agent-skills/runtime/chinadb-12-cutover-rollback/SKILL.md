---
name: chinadb-12-cutover-rollback
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Cutover, Rehearsal & Rollback. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "12-cutover-rollback"
  source_path: "skills/12-cutover-rollback/SKILL.md"
  source_sha256: "sha256:cae703d92168691986523cc422720554b3be59bd26650024270b47e5a59b9187"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Cutover, Rehearsal & Rollback

- **Skill ID:** `12-cutover-rollback`
- **Version:** `1.0.0`
- **Category:** core/operations
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Execute repeatable production-like rehearsals and a guarded cutover with drain/freeze/catch-up/switch/observe/rollback checkpoints and measured RPO/RTO.

## Inputs

- Certified release candidate
- CDC/catch-up state
- Deployment/runbook topology
- Traffic switch mechanism
- Rollback stream/backup plan
- Maintenance window

## Required outputs

- Rehearsal evidence
- Cutover runbook generated from route plan
- Measured RPO/RTO
- Go/no-go checkpoints
- Rollback evidence

## Implementation modules / repository contract

- ops/rehearsal.py
- ops/cutover.py
- ops/traffic_switch.py
- ops/catchup.py
- ops/rollback.py
- ops/runbook.py

## Interfaces and contracts

- Cutover requires orchestrator approval gate
- Rollback triggers are machine-readable and human-readable

## Workflow

1. Rehearse full cutover on production-like data/topology.
2. Verify backups and target restore before production cutover.
3. Drain or freeze writes according to route policy.
4. Catch CDC to declared safe position and reconcile.
5. Switch application/config/traffic with health checks.
6. Observe functional, data and performance probes.
7. Rollback on predeclared triggers; prove reverse path or restore procedure.
8. Record exact timings and positions.

## Mandatory tests

- Failed CDC catch-up
- Partial app deployment
- Health check failure
- Rollback after target writes
- DNS/config propagation delay
- Sequence divergence
- Emergency read-only mode

## Required evidence

- Rehearsal logs
- Cutover positions/timestamps
- RPO/RTO measurements
- Rollback success evidence
- E5 operational readiness inputs

## Fail-closed / escalation rules

- No first-ever cutover procedure may be attempted in production without rehearsal.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `12-cutover-rollback`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
