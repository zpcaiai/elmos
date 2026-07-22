# Batch 6 dependency semantic migration protocol v1

## Authority and inputs

Consume the frozen Batch 1 Build Model and dependency graph, Batch 2 symbol/call evidence, Batch 3 UIR semantics, Batch 4 target profile/module map, and Batch 5 conformance. A module not admitted by Batch 5 stays blocked. Every observation carries snapshot/run/module IDs and evidence references.

## Required pipeline

`declared coordinate -> exact resolved graph -> actual API use -> semantic profile -> provenance-bearing candidates -> compatibility score -> license/security/platform gate -> strategy -> adapters or runtime boundary -> declarative build patch -> resolver evidence -> API/differential validation`

Never infer equivalence from package names, descriptions, embeddings, popularity, or a high aggregate score. A blocking semantic, platform, license, vulnerability, provenance, or support condition always overrides ranking.

## Strategies

Prefer, in order allowed by evidence: remove proven-unused dependency; target standard library; approved target-native implementation; ecosystem package; generated adapter; governed compatibility runtime; in-process wrapper; sidecar; remote service; retained source runtime; manual review. `PROHIBITED` is a gate outcome, not an implementation shortcut.

No observed use means removable only when the analyzer reports complete coverage with no unresolved dynamic/reflection/native-load paths. Otherwise classify as unknown.

## Workspace ownership

Write governed artifacts under `dependencies/`, `knowledge/`, `mappings/`, `patches/`, `reports/`, and `logs/`. Generated target artifacts belong under `target-repository/adapters`, `target-repository/compatibility-runtime`, `target-repository/clients`, `target-repository/contracts`, `target-repository/deployment`, and `target-repository/build-files`. Boundary artifacts belong under `boundaries/wrappers`, `boundaries/sidecars`, `boundaries/remote-services`, `boundaries/retained-runtimes`, and `boundaries/serialization-schemas`.

Core planning never contacts registries, installs packages, runs lifecycle scripts, edits lockfiles by hand, or silently modifies human-owned target files. Registry and OSV-like data, licenses, platform support, build resolution, and contract results arrive through authoritative providers with timestamps and provenance.

## Gates

- D-A: normalized inventory and exact resolved graph are complete and source-scoped.
- D-B: every dependency has a proven-used/unused/unknown classification, semantic profile, and explicit strategy or blocker.
- D-C: selected artifacts pass version/platform/support and supply-chain policy; adapters/boundaries are planned; a sandboxed target resolver regenerates locks and passes resolution without lifecycle scripts.
- D-D: signature, API-contract, behavioral/differential, lifecycle, serialization, and service-boundary obligations pass for the selected strategy. Only D-D modules are eligible for Batch 7; D-D is not overall behavioral equivalence.

`NOT_RUN`, `BLOCKED`, `INCONCLUSIVE`, and missing evidence never render as `PASSED`. Preserve deterministic IDs, reversible patch plans, open obligations, and rejected alternatives.
