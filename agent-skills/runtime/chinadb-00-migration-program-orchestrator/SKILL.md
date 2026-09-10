---
name: chinadb-00-migration-program-orchestrator
description: "Use when ELMOS must follow the ChinaDB commercial database-migration specification for Migration Program Orchestrator. Keep exact directed route and version semantics, require real evidence, and fail closed on unsupported behavior."
metadata:
  source_package: "chinadb-commercial-migration-skills"
  source_version: "1.0.0"
  source_directory: "00-migration-program-orchestrator"
  source_path: "skills/00-migration-program-orchestrator/SKILL.md"
  source_sha256: "sha256:9889ffc5b74c9676ffd24d9301465faf6d22ba2798107de8cba5a4f4e64acdd5"
  normalized_namespace: "chinadb-commercial-migration-v1"
  implementation_state: "SPEC_ONLY"
  external_evidence_status: "NOT_RUN"
  production_certification: "NOT_CERTIFIED"
---
# Migration Program Orchestrator

- **Skill ID:** `00-migration-program-orchestrator`
- **Version:** `1.0.0`
- **Category:** core/orchestration
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Plan and execute an end-to-end migration route as a state machine. It owns dependency ordering, checkpoints, approvals, resume/retry, evidence aggregation and E1-E5 gate decisions; it does not implement target SQL rules itself.

## Inputs

- Route manifest: source/target engine, version, compatibility mode
- Application repositories and deployment topology
- SLO/RPO/RTO and maintenance-window constraints
- Secrets by reference only
- Selected source, application and target adapters

## Required outputs

- `migration-plan.json` DAG/state-machine
- Route-scoped workspace and immutable run id
- Checkpoint/resume journal
- Aggregated evidence index
- Final certification request or blocking report

## Implementation modules / repository contract

- `orchestrator/plan.py`
- `orchestrator/state_machine.py`
- `orchestrator/checkpoints.py`
- `orchestrator/approvals.py`
- `orchestrator/evidence_index.py`

## Interfaces and contracts

- Consumes `schemas/route-manifest.schema.json`
- Emits evidence conforming to `schemas/evidence.schema.json`
- All stages implement `plan/execute/verify/rollback` hooks

## Workflow

1. Validate the route manifest and adapter versions.
2. Run inventory and compatibility assessment before conversion.
3. Generate dependency graph: security/network -> schema -> data -> CDC -> code -> verification -> perf -> rehearsal -> cutover.
4. Execute idempotent stages with checkpoints and deterministic run ids.
5. Stop on critical unsupported semantics or failed gates; never auto-waive.
6. Aggregate all evidence and invoke production certification.

## Mandatory tests

- Crash/resume at every stage boundary
- Idempotent rerun after partial full-load
- Approval-gated repair and cutover
- Concurrent independent route runs
- Evidence tamper/fingerprint mismatch
- Failed target adapter capability discovery

## Required evidence

- State transition log
- Route fingerprint
- Stage timing and exit status
- Approval records
- Final evidence manifest

## Fail-closed / escalation rules

- Do not continue if target version/mode is unknown.
- Do not infer a waiver from a warning.
- Do not cut over when any mandatory E1-E5 gate is red.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.

## Repository Integration Boundary

- Provenance is pinned to `chinadb-commercial-migration-skills` version `1.0.0`, source Skill `00-migration-program-orchestrator`, and the SHA-256 digest in frontmatter.
- Installation normalizes an invocable specification only; it does not implement a converter, adapter, data mover, verifier, repairer, cutover, or certification workflow.
- Repository state is `SPEC_ONLY`; implementation is `false`, evidence is empty / `NOT_RUN`, and production certification is `NOT_CERTIFIED`.
- Every database route remains directional and exact to engine version, edition, provider, mode, driver, charset, collation, time zone, extension, and workload scope.
- SQL and procedural transformations require typed semantic IR and real source/target execution; parser-only, regex-only, generated, synthetic, or self-verified output is not runtime proof.
- Unsupported, lossy, ambiguous, partial, unknown, or unreconciled semantics fail closed and must remain explicit.
- Customer or production data writes require a separately authorized workflow; use disposable, cloned, masked, or synthetic data by default.
- Only the applicable conservative Batch 31 gate may raise database migration readiness, and independent external evidence is still required for certification.
