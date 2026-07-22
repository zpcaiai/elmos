# Batch 35 advanced verification

Read the implementation, quality, oracle, solver, fuzzing, concurrency, assurance, and security policies before using a Batch 35 skill.

The repository implementation has three separate layers:

- 22 exact Skills (1265–1286), 13 JSON Schemas, 15 templates, scaffold/validation/gate tools, and 9 toolkit regression tests.
- `modules/advanced-verification`, a Java 21 bounded verification runtime for property, metamorphic, mutation, structured fuzz, model/protocol, concurrency, numeric, cross-domain invariant, oracle, counterexample, and assurance-case behavior.
- `verification-packs/elmos-local-advanced-verification`, an executable local rehearsal with 14 Java tests and replay evidence.

The local pack is `experimental` and `NOT_CERTIFIED`. Source-to-target migration equivalence, external SMT/symbolic execution, an independent holdout, representative production workloads, and independent approval remain `NOT_RUN`.
