# 03 — Requirements and Traceability

## Inventory

- Requirements: **305** — {'functional': 225, 'non-functional': 60, 'governance': 20}.
- Atomic Skills: **45**.
- Scenarios: **279**.
- Implementation tasks: **506**.

Each functional requirement maps to one Skill acceptance check, related scenarios and an implementation batch in `catalog/traceability.csv`. Global NFR and governance requirements apply to every relevant vertical slice.

## Requirement quality rule

A requirement is implementation-ready only when it has an owner, priority, risk, typed input/output, acceptance method, evidence obligation, failure behavior, authority, idempotency/checkpoint implications, telemetry, rollback and completion boundary.

## Change rule

When a requirement, Skill, Adapter, policy, model, compiler, database, runtime or evidence method changes, invalidate affected evidence and recompute the dependency closure before release.
