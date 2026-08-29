# E0–E5 Certification Standard v3

- **E0 Characterized** — immutable source, dialect/runtime inventory, source-native baseline, semantic-obligation graph.
- **E1 Frontend/Build Fidelity** — parsing, symbols, types, IR, target build and critical static semantic checks.
- **E2 Component Semantics** — unit/property/contract tests and semantic micro-fixtures across covered obligations.
- **E3 Differential Behavior** — source-target multi-oracle differential execution for representative repositories and stateful scenarios.
- **E4 Stress & Assurance** — fuzz/metamorphic/mutation, UB/concurrency/numeric/security/performance, runtime matrix and applicable formal/translation validation.
- **E5 Production Representative** — representative workload shadow/dual/canary, rollback/reconciliation, fresh attested native evidence, all critical obligations closed or explicitly approved with expiry.

No higher level can pass with a required lower-level gate `not-run`.
