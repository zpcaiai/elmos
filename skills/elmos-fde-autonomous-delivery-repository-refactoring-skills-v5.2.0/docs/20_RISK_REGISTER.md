# 20 — Product Risk Register

| ID | Risk | Class | Primary controls |
|---|---|---|---|
| R01 | False completeness | Critical | Coverage-state model; unknown/unsupported blockers; independent review |
| R02 | Incorrect behavior-preservation oracle | Critical | Domain invariants, characterization, differential, property and human approval |
| R03 | Unsafe autonomous edits | Critical | Default deny, workspace lease, atomic ChangeSet, result interception, no production writes |
| R04 | Duplicate canonical authority | Critical | Symbolic binding validation and zero new routable entries |
| R05 | Tenant or secret leakage | Critical | RLS/isolation, secret brokerage, verified context, egress and retention policy |
| R06 | Adapter/provider drift | High | Version negotiation, conformance suite, pinning and evidence invalidation |
| R07 | Analyzer false positives/negatives | High | Evidence fusion, confidence, tool-native result, runtime and independent validation |
| R08 | Large-repository cost/latency | High | Incremental graph, cache, sharding, budgets, backpressure and benchmarks |
| R09 | Data migration loss | Critical | Expand/migrate/contract, CDC, reconciliation, backups and rollback rehearsal |
| R10 | Shadow path creates side effects | Critical | Effect suppression, read-only adapters, idempotency and reconciliation |
| R11 | Customer scope/adoption failure | High | Discovery, SOW/change control, champions, value telemetry and feedback |
| R12 | Generated package mistaken for implementation | High | BUILD_REPORT limits, runtime gates and E3 maximum |
