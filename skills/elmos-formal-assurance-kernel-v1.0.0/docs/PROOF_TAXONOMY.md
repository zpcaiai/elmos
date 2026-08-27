# Proof Taxonomy

| Property kind | Question | Primary method | Common fallback |
|---|---|---|---|
| Functional correctness | Does an implementation satisfy pre/post/invariants? | Hoare logic, weakest preconditions, JML/Dafny | symbolic tests |
| Trace refinement | Does target behavior stay within source behavior? | simulation, product program, trace inclusion | differential execution |
| Query equivalence | Do SQL queries return the same bag/set/order? | SQL equivalence prover, SMT | bounded counterexample database |
| Schema losslessness | Is information preserved by schema mapping? | relational algebra, round-trip proof | exhaustive bounded instances |
| State invariant | Can a bad state become reachable? | induction, SMT/TLA+/Alloy | runtime invariant monitor |
| Temporal safety | Does something bad never happen? | model checking | failure-injection tests |
| Liveness | Does progress eventually happen under assumptions? | LTL/fairness proof | long-running chaos tests |
| Noninterference | Can tenant/secret A affect observations of B? | relational verification/self-composition | taint + adversarial tests |
| Termination | Does a loop/workflow stop? | ranking function/decreases | hard iteration budget |
| Resource bound | Is token/time/memory bounded? | abstract interpretation/amortized contract | runtime quota |
| Route completeness | Are legacy routes preserved and unambiguous? | automata/SMT/Alloy | route corpus |
| Authorization dominance | Does authorization precede every protected effect? | control-flow dominance/model checking | security integration tests |

## Selection rules

- Pure deterministic functions favor SMT/product programs.
- Mutable heaps need frame conditions and heap relations.
- Distributed workflows need explicit state and failure models.
- Dynamic languages require a versioned semantic profile and runtime boundaries.
- SQL requires bag, NULL, type, collation, time and error semantics.
- Concurrency claims must state memory model and schedule bound.
- Liveness always lists fairness and environment-recovery assumptions.

## Proof obligation anatomy

Every obligation contains:

```text
subject
property kind
formal formula
source map
criticality
required assurance
allowed proof modes
explicit assumptions
dependencies
semantic profile/model
resource budget
failure policy
```

An obligation without these fields is an experiment, not production evidence.
