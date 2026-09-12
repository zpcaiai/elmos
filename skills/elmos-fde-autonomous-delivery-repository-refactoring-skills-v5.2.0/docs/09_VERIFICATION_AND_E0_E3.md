# 09 — Verification and E0–E3 Readiness

## Proof mesh

1. inventory/build and environment evidence;
2. type/static/dataflow/architecture/security/supply-chain checks;
3. existing + characterization + unit/integration/contract/E2E tests;
4. property, metamorphic, differential, record/replay and snapshot oracles;
5. mutation/fuzz/concurrency/performance/soak/chaos/recovery;
6. formal routing for high-risk state, permission, consistency and conservation properties;
7. independent evidence assembly and K8 recommendation.

## E0–E3

- E0: scope/inventory/custody known.
- E1: build/runtime is reproducible or the exact blocker is proved.
- E2: critical behavior, contracts and invariants have executable oracles.
- E3: relevant security, performance, reliability, migration and rollback preparation pass in authorized non-production environments.

E4/E5/P05, customer production traffic, soak and certification are outside this package. Producer summaries are never sufficient evidence.
