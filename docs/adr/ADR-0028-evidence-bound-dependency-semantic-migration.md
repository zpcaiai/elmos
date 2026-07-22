# ADR-0028: Evidence-bound dependency semantic migration

- Status: Accepted
- Date: 2026-07-21

## Context

Cross-language migration cannot replace a dependency safely from package names or declared coordinates. The source may use only a small but semantically sensitive API subset; resolution, runtime loading, licenses, native assets, lifecycle, serialization and platform support can differ even between apparently similar libraries. Batch 5 produces target-language bodies but deliberately leaves external dependency semantics open.

## Decision

Batch 6 uses an evidence chain from normalized declaration and exact resolved graph through actual used APIs and a semantic profile to provenance-bearing target candidates. Compatibility ranking is multi-dimensional, but blockers are non-compensating: incomplete API coverage, semantic gaps, target-policy prohibition, unsupported platform, unknown license/vulnerability/provenance, or an unpinned artifact cannot be averaged into a pass.

The strategy ladder includes proven removal, target standard library, approved native or ecosystem packages, generated adapters, a governed compatibility runtime, in-process wrappers, sidecars, remote services, retained source runtimes and manual review. Boundary strategies are valid architecture outcomes. Each defines serialization, lifecycle, threading, resources, security, deployment, support and exit obligations.

The core module is offline and pure. Registry catalogs, resolved graphs, supply-chain assessments, target build resolution and differential validation are injected authorities with evidence references and timestamps. The core never guesses from the network, installs packages, runs lifecycle scripts, edits lockfiles by hand, or mutates a target repository. It emits reversible build patch plans; an ecosystem-aware sandbox backend regenerates locks and returns exact resolution evidence.

Per-module gates D-A through D-D cover inventory/graph, use/semantic strategy, supply-chain/build readiness and API/differential validation. Only D-D modules may enter Batch 7, and D-D does not claim whole-system behavioral equivalence.

## Consequences

- A complete analyzer run is required before an unobserved dependency may be removed.
- High-scoring but policy-blocked candidates stay rejected and auditable.
- Compatibility runtime and retained-runtime code become versioned, owned product components rather than hidden utilities.
- Real D-C and D-D require external resolver, vulnerability/license and differential-test evidence; local unit tests validate orchestration and fail-closed behavior only.
