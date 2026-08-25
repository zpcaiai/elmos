---
name: elmos-architecture-contract-governance
description: Freeze service boundaries, authoritative state ownership, identifiers,
  lifecycle enums, APIs, schemas, and architecture decisions.
version: 1.0.0
priority: P0
phase: G0
dependencies:
- elmos-infrastructure-program-orchestrator
---

# Architecture and Contract Governance

## Objective

Create a stable architecture and contract foundation shared by every infrastructure component.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Architecture and Contract Governance** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-infrastructure-program-orchestrator`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Keep a modular monolith unless measured scale or isolation justifies a process boundary.
- PostgreSQL is authoritative for business state, Temporal for workflow history, and CAS for immutable content.
- Redis and event streams are never the only authoritative task, workflow, artifact, or approval store.
- Every external or cross-process contract is versioned and compatibility-tested.

## Required inputs

- Module and deployment inventory.
- OpenAPI, Protobuf, JSON Schema, database migrations, event definitions, and ADRs.
- Current runtime modes.

## Required outputs

- `Reference architecture and authority matrix.`
- `Versioned contract catalog.`
- `Identifier and lifecycle specification.`
- `ADRs and compatibility CI.`

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

### Architecture inventory

- [ ] `ELMOS-ARCH-001` Inventory each module, entry point, dependency, persistent state, network endpoint, and deployment mode.
- [ ] `ELMOS-ARCH-002` Draw control, workflow, execution, artifact, model, policy, evidence, data, and observability planes.
- [ ] `ELMOS-ARCH-003` Assign one authoritative owner for every core state domain.
- [ ] `ELMOS-ARCH-004` Find process-local state that would be lost on restart and assign a durable store.
- [ ] `ELMOS-ARCH-005` Mark modules that remain inside the modular monolith and justified independent workers.
### Architecture decisions

- [ ] `ELMOS-ARCH-006` Write an ADR for Temporal versus a custom workflow engine.
- [ ] `ELMOS-ARCH-007` Write an ADR for content-addressed storage versus project copying.
- [ ] `ELMOS-ARCH-008` Write an ADR for private-runner source residency.
- [ ] `ELMOS-ARCH-009` Write an ADR for deterministic rules before LLM repair.
- [ ] `ELMOS-ARCH-010` Write an ADR for event-plane responsibilities and why it does not replace workflows.
- [ ] `ELMOS-ARCH-011` Define ADR states proposed, accepted, superseded, rejected, and deprecated.
### Identifiers and states

- [ ] `ELMOS-ARCH-012` Standardize tenant, user, repository, snapshot, project, workflow, task, attempt, runner, artifact, evidence, approval, and policy identifiers.
- [ ] `ELMOS-ARCH-013` Replace free-form status strings with versioned enums.
- [ ] `ELMOS-ARCH-014` Define allowed state transitions and terminal states.
- [ ] `ELMOS-ARCH-015` Define idempotency key, receipt, transition ID, fencing token, correlation ID, trace ID, and audit ID formats.
- [ ] `ELMOS-ARCH-016` Add database uniqueness and transition constraints.
### API and schema governance

- [ ] `ELMOS-ARCH-017` Version external APIs under /api/v1 and define deprecation policy.
- [ ] `ELMOS-ARCH-018` Define a uniform error envelope with code, message, retryable, correlation_id, and details.
- [ ] `ELMOS-ARCH-019` Define pagination, filtering, sorting, ETag, conditional update, and idempotency semantics.
- [ ] `ELMOS-ARCH-020` Add schema_version to every cross-module DTO and event.
- [ ] `ELMOS-ARCH-021` Generate clients from OpenAPI and bindings from Protobuf.
- [ ] `ELMOS-ARCH-022` Reject removed required fields, reused Protobuf numbers, and incompatible enum changes in CI.
- [ ] `ELMOS-ARCH-023` Adopt canonical repository directories and ownership rules.

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

- [ ] Generate clients and verify no contract drift.
- [ ] Run compatibility tests against the previous released contracts.
- [ ] Test illegal transitions and duplicate identifiers.
- [ ] Verify no core production state exists only in process memory.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Every core object has a schema, stable ID, lifecycle, and authority.
- [ ] Breaking contract changes fail CI.
- [ ] Architecture boundaries are documented and enforced.
- [ ] No EPIC depends on undefined ownership or lifecycle semantics.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
