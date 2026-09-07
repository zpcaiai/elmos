# Implementation Guide — Property, Metamorphic, Mutation and Fuzz Controller

## Purpose

Discover deep semantic defects through generated properties, metamorphic relations, mutation testing and coverage-guided fuzzing with minimized counterexamples.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Derive properties from contracts and invariants
2. Generate domain-specific metamorphic transformations
3. Measure test sensitivity with semantic mutants
4. Run bounded coverage-guided fuzzing
5. Shrink failures into stable regression cases

## Native acceptance corpus

- `ELMOS_PROPERTY_METAMORPHIC_MUTATION_FUZZ_CONTROLLER-01` — serialization round trip
- `ELMOS_PROPERTY_METAMORPHIC_MUTATION_FUZZ_CONTROLLER-02` — order/permutation relation
- `ELMOS_PROPERTY_METAMORPHIC_MUTATION_FUZZ_CONTROLLER-03` — idempotency property
- `ELMOS_PROPERTY_METAMORPHIC_MUTATION_FUZZ_CONTROLLER-04` — semantic mutation kill
- `ELMOS_PROPERTY_METAMORPHIC_MUTATION_FUZZ_CONTROLLER-05` — parser/API fuzz
- `ELMOS_PROPERTY_METAMORPHIC_MUTATION_FUZZ_CONTROLLER-06` — resource-bound fuzz
- `ELMOS_PROPERTY_METAMORPHIC_MUTATION_FUZZ_CONTROLLER-07` — counterexample shrinking

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
