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
