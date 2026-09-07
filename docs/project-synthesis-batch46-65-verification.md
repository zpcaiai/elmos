# Project Synthesis Batch 46–65 verification

## Integrated scope

- PG001–PG170 remain the Batch 46–60 requirements, architecture, generation, language, integration, test, build and delivery specifications.
- PG171–PG222 add safe change/regeneration, governed Agent and Skill runtime contracts, independent product evaluation, ten Domain Packs, Requirement Studio, tenant policy, usage metering, diagnostics and feedback governance.
- The combined validator requires 222 contiguous identifiers across Batch 46–65 and 23 schemas including the repository synthesis request contract.

## Runnable engineering evidence

`make project-synthesis` validates the complete specification set, runs the Project Synthesis engine tests and static analysis, and exercises every locally available member of the eight-target starter matrix: Java, Python, C#, TypeScript, Go, Kotlin, PHP, and Rust. `scripts/run_acceptance.py --require-all-toolchains` is the strict command when all eight exact toolchains must be present; unavailable native checks remain explicit instead of being counted as passed.

Every generated workspace now contains a hash-bound project-structure graph, declared-dependency graph, requirements-to-target semantic mapping, native target status, and a complete selected-target pair matrix. `docs/PROJECT_INSIGHTS.md` renders those dimensions as Mermaid graphs and exact status tables. Greenfield requirement mapping is not source/target equivalence, so direct semantic and behavioral pair checks remain `NOT_RUN` until separately executed.

The runnable generator remains the bounded one-aggregate CRUD/in-memory Starter documented in the Batch 46–60 verification record. The Batch 61–65 import extends governed Skill behavior and validation contracts; it does not by itself implement persistent multi-agent scheduling, Marketplace publication, Requirement Studio UI, tenant billing, external deployment or independent product certification.

## Evidence boundary

Local validation can establish specification integrity and starter-profile engineering readiness. Drift reconciliation against customer repositories, protected manual-edit regeneration, production sandbox enforcement, external domain-owner approval, independent certification, real tenant isolation, Marketplace operations, usage billing, support diagnostics and governed feedback promotion remain `NOT_RUN` until executed in authorized environments with immutable evidence.

Commands:

```sh
make project-synthesis
uv --directory engines/project-synthesis-engine run --locked python scripts/run_acceptance.py --require-all-toolchains
make test-suite-1-65-check
make test-suite-1-65-gate
```

The last command is expected to return a non-zero status while the 750 supplemental field cases are `NOT_RUN`.
