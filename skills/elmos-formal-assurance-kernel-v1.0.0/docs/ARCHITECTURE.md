# Formal Assurance Plane Architecture

## 1. Position

The package adds a horizontal `Formal Assurance Plane` beside Elmos planning, generation, conversion, testing and deployment planes. It does not replace tests. It produces explicit specifications, proof obligations, model-checking results, counterexamples, assumptions and release decisions.

```text
Requirements / Source Repository / SQL / Runtime Design
                         |
              Evidence-preserving ingestion
                         |
      Formal Spec IR + Observation Contract + Assumptions
                         |
             Proof Obligation Planner (DAG)
                         |
       Verifier Portfolio Router + Policy Kernel
                         |
        Durable Orchestrator / Secretless Sandboxes
                         |
  Lean | SMT | TLA+ | Alloy | JML | SQL | Runtime monitors
                         |
 Immutable Evidence Store + Counterexample-to-Test
                         |
       Coverage + Drift + Waiver + Release Gate
                         |
         Engineering / Audit / Customer Reports
```

## 2. Control-plane invariants

- The machine source of truth is the canonical proof result, never rendered prose.
- Every run binds formula, source, target, semantic profile, semantic model, assumptions, TCB, engine options and bound.
- One proof run has at most one valid owner lease.
- A stale fencing token cannot commit a result, checkpoint, artifact or billing event.
- A terminal run cannot regress to a nonterminal state.
- The account-level top-level concurrency limit is three.
- Credit is reserved before work and one usage event is charged at most once.
- Bounded, unknown, unsupported and waived results retain their exact status.

## 3. Data plane

PostgreSQL 17 stores metadata and durable state. Large artifacts are immutable objects in tenant-scoped object storage. Events use an outbox-compatible bus. OpenTelemetry carries trace correlation without embedding source formulas in high-cardinality labels.

## 4. Trust boundaries

The orchestrator, specification compiler and status policy are trusted service components. External verifiers run in isolated, no-network, no-secret sandboxes. Kernel-checked certificates and solver-trusted results are distinct assurance classes. The package never assumes the external tool is installed merely because an adapter exists.

## 5. Composition strategy

Repository-level assurance is composed from:

```text
function contract
→ module assume/guarantee
→ service protocol
→ API/effect trace
→ repository entrypoint coverage
```

Strong repository claims require every relevant entrypoint to participate in the composition graph. An uncovered endpoint, dynamic target or native boundary prevents full certification and is reported rather than averaged away.

## 6. High availability

The production implementation should use durable workflows, transactional outbox, idempotent commands, lease/fencing, checkpoint-compatible adapters, object-store integrity checks, and PostgreSQL point-in-time recovery. Solver workers are disposable; evidence and state are authoritative outside the worker.

## 7. Extensibility

New proof engines implement `contracts/schemas/verifier-adapter.schema.json`, pass conformance fixtures and are registered in the TCB. New business lines emit Formal Spec IR and proof obligations; they do not bypass proof status or evidence policy.
