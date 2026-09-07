# ADR-0036: Evidence-bound build, test and repair loop

## Status

Accepted

## Context

Generated target repositories can contain dependency, compiler, analyzer, test-translation,
fixture and runtime failures. A Coding Agent can propose useful long-tail fixes, but an unbounded
Agent that edits files directly can hide failures, weaken tests, change contracts, consume
unlimited budget or leave a repository between Snapshots. A passing build alone does not prove a
repeatable green baseline.

## Decision

Extend `modules/repair-orchestration` with a Batch 8 control plane that:

- admits only frozen, comparable source/target baselines and Batch 7-eligible modules;
- plans a minimum sufficient polyglot matrix and version-bound command records;
- delegates all repository execution to an isolated `ExecutionAuthority`;
- preserves native diagnostic evidence while normalizing stable fingerprints;
- clusters and attributes failures before selecting a repair;
- tries deterministic recipes before bounded Agent patches;
- binds one structured patch to one cluster, plan, scope and base Snapshot;
- independently inspects actual diff scope, boundaries, contracts, tests, dependencies and suppressions;
- delegates atomic apply/rollback to a `TransactionalPatchAuthority`;
- requires affected-scope and clean full-regression evidence from an independent authority;
- rejects test deletion/assertion weakening, suppression/dynamic growth, unapproved dependencies,
  manual-region edits, silent contract drift and unreviewed high-risk Agent changes;
- stops on convergence, environment, risk, budget, oscillation, no progress or human decision;
- writes compressed, immutable, symlink-safe evidence outside the target repository.

Evaluate R-A through R-D per module. Require matching clean-environment runs for R-D. Treat R-D as
admission to Batch 9 behavioral equivalence, not production readiness or equivalence proof.

## Consequences

The core is deterministic and testable without executing customer code. Real Maven/Gradle, Python,
MSBuild, Node, analyzer, test, service and Agent execution remains a deployment capability. When an
approved sandbox, registry, test resource or native tool is unavailable, the result remains
`NOT_RUN`, `BLOCKED` or `INCONCLUSIVE`.

The repository retains the earlier Agent routing APIs in `repair-orchestration`; the new
`RepairLoop*` types are additive and do not reinterpret older delivery Batch numbering.
