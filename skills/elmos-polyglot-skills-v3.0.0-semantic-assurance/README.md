# ELMOS Polyglot Repository Semantic Compiler Skills v3.0.0

This is the complete merged package: **300 Skills** = previous 168 polyglot/legacy Skills + **132 semantic assurance Skills**.

## Why v3

v3 upgrades language conversion from syntax/AST transformation to explicit **semantic preservation and production certification**. Correctness is represented as route-specific semantic obligations and observable behavior relations. Compilation, generated LOC, test count, or static package validation cannot certify conversion.

## Scale

- 300 implementation/execution Skills
- 28 primary technology surfaces + 8 legacy repository DSL surfaces
- 784 route cells, 40 reference/Golden Route profiles
- 40 route certification plans registered, all `not-run` by default
- 132 new Skills across 9 batches J–R
- 10 new machine-readable assurance schemas
- E0–E5 certification v3

## New batches

- **Batch J**: 16 Skills
- **Batch K**: 14 Skills
- **Batch L**: 16 Skills
- **Batch M**: 18 Skills
- **Batch N**: 16 Skills
- **Batch O**: 14 Skills
- **Batch P**: 12 Skills
- **Batch Q**: 14 Skills
- **Batch R**: 12 Skills

### J — Frontend/Syntax Fidelity
Lossless CST, dialect/version detection, preprocessing, source roundtrip, native AST cross-checking, symbol/scope/dispatch and reflection/dynamic frontend consistency.

### K — Type Semantics
Canonical type algebra, nullability, numeric domains, string/codepoint, collections, generics/variance/erasure, contracts, ownership and API compatibility.

### L — Control/Data/Effects
CFG/SSA/PDG, aliasing, call graph, side effects, exceptions, resources, closures, generators, async, reflection, runtime codegen and nondeterminism.

### M — Runtime Edge Semantics
Memory models, ABI/FFI/layout, atomics/locks/actors, UB/sanitizers, IEEE-754, money decimal, timezone, encoding/collation, binary records and SQL isolation.

### N — Behavior Equivalence Oracles
Multi-oracle differential execution, trace/state/DB/message/file/network/API/UI equivalence, performance/security equivalence, replay and refinement counterexamples.

### O — Fixture & Certification Corpus
Normative/spec mapping, grammar/semantic coverage, dialect matrices, adversarial/legacy/repository/generated/bug corpora, minimization, freshness and readiness gate.

### P — Native Runtime Lab
Hermetic toolchains plus mainframe, IBM i, Windows legacy, SAP, HPC, mobile, browser/Wasm and database/message labs with attested evidence.

### Q — Formal & Translation Validation
Formal semantics contracts, LLVM refinement, SMT, symbolic execution, BMC, abstract interpretation, proof obligations, verified lowering, Wasm oracle and proof counterexample replay.

### R — Semantic Stress Testing
Grammar/differential fuzzing, metamorphic/property testing, compiler N-version oracle, UB filter, mutation testing, reducer and bug feedback loop.

## Certification model

See `references/e0-e5-certification-standard-v3.md`. Every route must close applicable critical semantic obligations. `unknown`, `timeout`, missing native runtime and stale evidence do not become `pass`.

## Validate

```bash
./validate.sh
```

## Install

```bash
./install.sh /path/to/elmos
```

Use `--force` only after reviewing collisions.

## Important boundary

Package validation proves that the Skills/contracts/schemas/registries/installers are structurally consistent. It does **not** claim the 40 Golden Routes or 784 route cells have already earned E5 on real production environments.
