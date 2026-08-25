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
