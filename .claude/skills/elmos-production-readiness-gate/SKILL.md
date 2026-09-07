---
name: elmos-production-readiness-gate
description: Evaluate the complete eLMOS platform against security, reliability, reproducibility,
  quality, evidence, observability, cost, recovery, scale, and pilot criteria and
  emit a conservative release status.
version: 1.0.0
priority: P0
phase: G9
dependencies:
- elmos-infrastructure-program-orchestrator
- elmos-java-migration-production-loop
- elmos-scale-benchmark-certification
---

# Production Readiness and Commercial Release Gate

## Objective

Prevent a structurally valid Skill package or partially implemented platform from being presented as production-ready without executed evidence.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Production Readiness and Commercial Release Gate** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-infrastructure-program-orchestrator`
- `elmos-java-migration-production-loop`
- `elmos-scale-benchmark-certification`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Static file/package validation is not implementation or production proof.
- Every gate cites executed evidence with exact snapshot/toolchain/policy versions.
- Missing, stale, ambiguous, or failed mandatory evidence blocks or limits release.
- Exceptions cannot self-approve or suppress critical findings.

## Required inputs

- All program manifests, task reports, tests, benchmark/security/DR/pilot evidence, risks, exceptions, and SLO/cost data.
- Requested release scope, tenants, languages, deployment modes, and certification level.

## Required outputs

- `Readiness matrix and blocking issues.`
- `CERTIFIED, LIMITED, EXPERIMENTAL, or BLOCKED decision.`
- `Approved scope/conditions/expiry.`
- `Remediation plan and signed readiness evidence.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

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

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Run the gate against a documentation-only scaffold and require BLOCKED.
- [ ] Remove/expire mandatory security, DR, benchmark, or pilot evidence and require downgrade.
- [ ] Attempt self-approved exception and reject it.
- [ ] Limit a certified Java/private-runner scope from being claimed for unsupported languages/public SaaS.
- [ ] Tamper with readiness evidence and fail offline verification.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Production readiness is an executed, scoped, expiring, signed evidence decision.
- [ ] No static bundle or untested adapter is presented as production-complete.
- [ ] Commercial claims match the exact tested scope.
- [ ] Every blocking issue has an actionable owner and remediation path.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
