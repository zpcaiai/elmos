# Batch 35 product implementation

## Implemented runtime

`modules/advanced-verification` is a Java 21 library integrated into the root Maven reactor. It implements bounded, deterministic product primitives rather than placeholder success responses:

- seeded property evaluation with shrinking and replayable counterexamples;
- metamorphic relation evaluation;
- mutation score and critical-survivor blocking;
- structured bounded fuzzing with input and case budgets;
- model/protocol transition and liveness checks;
- deterministic schedule exploration with forbidden-outcome detection;
- bounded finite-domain proof results that distinguish proved-within-domain, disproved, unknown-budget-exhausted, and unsupported;
- decimal rounding, scale, tolerance, and integer-overflow verification;
- money/data conservation, denied-action side effects, tenant noninterference, and canonical query equivalence;
- oracle trust and independence governance;
- stable counterexample fingerprints and replay registry;
- assurance claims, evidence, review requirements, owned residual risk, and blockers.

The runtime deliberately does not label bounded enumeration as universal proof and does not embed an LLM as an authoritative oracle.

## Executable evidence

Run:

```bash
make -f Makefile.batch35 batch35-local-rehearsal
```

The rehearsal builds `modules/portfolio-scale` and `modules/advanced-verification`, executes the latter's 14 JUnit tests, records source, target, environment, test, negative-control, and replay evidence, validates the pack, and runs the only Batch 35 gate.

Expected conclusion:

```text
structural_gate_status=passed
certification_decision=NOT_CERTIFIED
```

## Evidence boundary

The local evidence proves that the repository implementation compiles and its bounded behaviors execute in the declared Java 21 environment. It does not prove behavioral equivalence for a real migration route, universal formal correctness, production safety, or customer certification. External SMT/symbolic execution, independent holdout data, representative production workloads, independent review, and approval remain `NOT_RUN`.
