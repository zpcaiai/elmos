# Architecture and Contract Governance

- Skill: `elmos-architecture-contract-governance`
- Priority: `P0`
- Phase: `G0`
- Dependencies: `elmos-infrastructure-program-orchestrator`

## Objective

Create a stable architecture and contract foundation shared by every infrastructure component.

## Task groups

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

## Validation

- [ ] Generate clients and verify no contract drift.
- [ ] Run compatibility tests against the previous released contracts.
- [ ] Test illegal transitions and duplicate identifiers.
- [ ] Verify no core production state exists only in process memory.

## Exit gate

- [ ] Every core object has a schema, stable ID, lifecycle, and authority.
- [ ] Breaking contract changes fail CI.
- [ ] Architecture boundaries are documented and enforced.
- [ ] No EPIC depends on undefined ownership or lifecycle semantics.
