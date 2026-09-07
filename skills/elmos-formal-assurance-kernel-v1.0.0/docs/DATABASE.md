# Database Design

## Core aggregates

- `formal_spec`: frozen, versioned specification and source map.
- `proof_assumption`: explicit environmental/trust assumptions.
- `proof_obligation`: atomic formal property.
- `proof_plan` and edges: acyclic execution DAG.
- `proof_run`: durable lease, fencing, mode, result and timing.
- `proof_artifact`: immutable content-addressed evidence.
- `proof_counterexample`: minimized replayable witness.
- `trusted_component`: TCB version/digest/SBOM/signature.
- `proof_waiver`: four-eyes risk acceptance.
- `proof_coverage_snapshot`: immutable coverage snapshot.
- `release_gate_decision`: authoritative decision history.
- `proof_cache`: exact dependency-keyed reuse.
- `proof_dependency`: drift impact graph.
- `runtime_monitor`: operational boundary.

## Tenancy

RLS uses `current_setting('elmos.tenant_id', true)`. The service must set the tenant inside every transaction and must use a database role that cannot bypass RLS for ordinary requests. Platform audit access uses a separate audited role, not an application flag.

## Immutability

Proof artifacts cannot be updated or deleted through normal SQL. Corrected evidence is a new artifact/run. Gate decisions are append-only. Historical statuses remain available even when marked stale.

## Cache key

The cache key includes formula, semantic profile/model, assumptions, TCB, engine/version/digest/options, bound, source and target hashes. Omitting any dimension can create an unsound cache hit.

## Partitioning

At high scale, partition `proof_event`, `proof_run` and coverage history by month and optionally tenant hash. Retention policies must preserve evidence referenced by active release decisions.
