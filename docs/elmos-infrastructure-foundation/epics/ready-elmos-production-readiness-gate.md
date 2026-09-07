# Production Readiness and Commercial Release Gate

- Skill: `elmos-production-readiness-gate`
- Priority: `P0`
- Phase: `G9`
- Dependencies: `elmos-infrastructure-program-orchestrator`, `elmos-java-migration-production-loop`, `elmos-scale-benchmark-certification`

## Objective

Prevent a structurally valid Skill package or partially implemented platform from being presented as production-ready without executed evidence.

## Task groups

### Implementation completeness

- [ ] `ELMOS-READY-001` Verify every required repository module, migration, API/schema, runner adapter, policy, dashboard, runbook, installer, and operational job exists in the target repository.
- [ ] `ELMOS-READY-002` Require code review, unit/integration/end-to-end tests, failure-path tests, and clean-environment reproduction.
- [ ] `ELMOS-READY-003` Distinguish generated task definitions from executed implementation.
- [ ] `ELMOS-READY-004` Reject placeholder, TODO-only, mock-only, or documentation-only completion for production gates.

### Security and tenancy gate

- [ ] `ELMOS-READY-005` Require trusted OIDC, membership-derived tenant, resource authorization, effective all-table RLS with non-superuser runtime role, unique rotating runner identity, short-lived secrets, sandbox/egress, audit, and cross-tenant attack tests.
- [ ] `ELMOS-READY-006` Require signed trusted toolchains/rules/skills/artifacts and passing supply-chain policy.
- [ ] `ELMOS-READY-007` Block unresolved critical/high security findings according to policy.

### Reliability and data gate

- [ ] `ELMOS-READY-008` Require idempotent workflow start/state transitions/side effects, lease renewal/reaper/fencing/reconciliation/cancel/checkpoint/replay, immutable snapshot/staging/CAS integrity, safe GC, and no duplicate PR/billing/export effects.
- [ ] `ELMOS-READY-009` Require backup restore and DR exercises within RPO/RTO.
- [ ] `ELMOS-READY-010` Require data retention/export/delete/legal-hold behavior.

### Transformation and quality gate

- [ ] `ELMOS-READY-011` Require reproducible toolchain/build, deterministic rules and second-run idempotency, semantic-gap reporting, preserved tests, compile/contract/behavior/performance/security validation, bounded agent repair, and certification evidence.
- [ ] `ELMOS-READY-012` Require no silent semantic loss or gate-gaming repairs.
- [ ] `ELMOS-READY-013` Define allowed Known Deviations and manual work.

### Operations and economics gate

- [ ] `ELMOS-READY-014` Require end-to-end trace/metrics/logs/redaction, tested alerts/runbooks, SLOs, capacity, cost ledger, budgets, source-egress metric, and calibrated machine wall-clock ETA.
- [ ] `ELMOS-READY-015` Require cost per verified work unit and forecast accuracy within declared tolerance.
- [ ] `ELMOS-READY-016` Keep human-equivalent effort comparison separate.

### Scale and pilot gate

- [ ] `ELMOS-READY-017` Require reproducible cold/warm/incremental/scale benchmarks, fault/security campaigns, restore/replay, and at least three repeatable authorized Java pilot repositories.
- [ ] `ELMOS-READY-018` Require reviewable PR/checks, signed offline evidence, explainable failure, customer merge control, and source-local default.
- [ ] `ELMOS-READY-019` Limit certification to actually tested languages, versions, deployment modes, scales, and security tiers.

### Decision and expiry

- [ ] `ELMOS-READY-020` Score each mandatory gate as PASS, FAIL, MISSING, STALE, WAIVED, or NOT_APPLICABLE with evidence digest.
- [ ] `ELMOS-READY-021` Emit CERTIFIED, LIMITED, EXPERIMENTAL, or BLOCKED and exact scope, conditions, expiry, owners, and remediation.
- [ ] `ELMOS-READY-022` Require independent approval for commercial release.
- [ ] `ELMOS-READY-023` Sign the readiness decision and include it in the release Evidence Pack.
- [ ] `ELMOS-READY-024` Automatically invalidate on critical source/toolchain/policy/schema/security/environment changes.

## Validation

- [ ] Run the gate against a documentation-only scaffold and require BLOCKED.
- [ ] Remove/expire mandatory security, DR, benchmark, or pilot evidence and require downgrade.
- [ ] Attempt self-approved exception and reject it.
- [ ] Limit a certified Java/private-runner scope from being claimed for unsupported languages/public SaaS.
- [ ] Tamper with readiness evidence and fail offline verification.

## Exit gate

- [ ] Production readiness is an executed, scoped, expiring, signed evidence decision.
- [ ] No static bundle or untested adapter is presented as production-complete.
- [ ] Commercial claims match the exact tested scope.
- [ ] Every blocking issue has an actionable owner and remediation path.
