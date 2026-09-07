# Verifier Toolchain Policy

## Portfolio

The package declares adapters for Z3, cvc5, Lean 4, Boogie, Dafny, TLC, Apalache, Alloy, OpenJML, KeY, Java PathFinder, K Framework, Alive2, SQLSolver, VeriEQL, Kani and Frama-C.

## Production enablement checklist

- exact version and OCI image digest;
- license approval;
- SBOM and vulnerability scan;
- signature/provenance verification;
- no-network/no-secret sandbox test;
- parser conformance tests for success, counterexample, timeout, crash and malformed output;
- known-soundness regression corpus;
- resource limits and cancellation;
- evidence replay;
- TCB registration.

## Routing

Capabilities are declared conservatively. A tool is eligible only when the obligation logic and language feature set are a subset of its conformance-tested profile. Unsupported features do not silently fall back to a result parser heuristic.

## Cross-checking

Use independent engines for the highest-risk transformations when feasible. Solver disagreement is a first-class conflict and blocks release. Proof certificates are preferred where practical, but solver-trusted evidence remains valid when accurately labeled.

## Version changes

A tool or adapter update creates a new TCB component. Existing proof evidence does not automatically inherit trust; impact analysis schedules replay or marks it stale.
