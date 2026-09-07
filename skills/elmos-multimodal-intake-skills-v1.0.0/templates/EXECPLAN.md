# ExecPlan: <title>

## Metadata

- Owner:
- Created:
- Updated:
- Primary Skill:
- Supporting Skills:
- Target repository/branch:
- Package version:
- Risk level:
- Rollout flag:

## Goal and user-visible outcome

Describe the finished behavior in observable terms. Include what the user can upload, see, recover, review or download.

## Existing repository findings

- Relevant modules/services:
- Existing data model:
- Existing APIs/events:
- Existing task/workflow behavior:
- Existing authz/tenant model:
- Existing storage/index/provider integrations:
- Reusable components:
- Conflicts/gaps:

## Scope

### In scope

- ...

### Out of scope

- ...

## Non-negotiable invariants

- [ ] Original assets immutable
- [ ] Tenant/project/version isolation
- [ ] Source anchors for key conclusions
- [ ] No content-as-instruction privilege
- [ ] Ingestion executes no user code
- [ ] Durable/idempotent recovery
- [ ] No duplicate side effects/cost
- [ ] No silent truncation/omission/version switch
- [ ] Machine wall-clock ETA
- [ ] Real tests and evidence before completion

## Design

### Components and ownership

| Component | Responsibility | Data owner | Existing/new |
|---|---|---|---|

### Data changes

| Migration | Table/object | Compatibility | Backfill | Rollback |
|---|---|---|---|---|

### API/event changes

| Contract | Version | Producer | Consumer | Idempotency |
|---|---|---|---|---|

### Security/trust changes

- New input/egress:
- Secrets:
- Sandbox:
- Tool permissions:
- Abuse limits:
- Audit:

### Context/cost/ETA changes

- Model capability dependency:
- Token budget:
- Cost attribution:
- ETA features:
- Failure/reconciliation:

## Implementation milestones

### Milestone 1 — <vertical slice>

- [ ] Code
- [ ] Migration
- [ ] API/event
- [ ] Authz/security
- [ ] Telemetry
- [ ] Unit/contract tests
- [ ] Integration/E2E evidence

### Milestone 2 — ...

## Test plan

| Test | Fixture | Command | Expected | Evidence path |
|---|---|---|---|---|

Include relevant: functional, provenance, security, archive, tenant isolation, long context, recovery, cost, performance, UI and deletion.

## Rollout

- Feature flags:
- Tenant cohort:
- Migration order:
- Backfill:
- Capacity:
- Alerts:
- Kill switch:
- Rollback:

## Progress log

### <date/time>

- Completed:
- Evidence:
- Decision:
- Blocker:
- Next:

## Final completion check

- [ ] All relevant Skill acceptance criteria pass
- [ ] No skipped relevant tests
- [ ] Migrations and rollback tested
- [ ] API/schema/docs updated
- [ ] Source/integrity report attached
- [ ] Security evidence attached
- [ ] P50/P95/P99 and reference hardware attached
- [ ] Machine wall-clock and cost report attached
- [ ] Remaining limitations disclosed
