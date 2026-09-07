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
