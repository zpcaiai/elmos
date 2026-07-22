# ADR-0019: Polyglot intake and unified migration manifest

- Status: Accepted
- Date: 2026-07-20

## Context

ELMOS began with a deterministic Java/Spring modernization path. Repository-to-repository translation across Java, Python, C# and JavaScript/TypeScript cannot safely scale as twelve independent language-pair pipelines: repository structure, dependencies, tests, resources and runtime semantics would diverge, while file-by-file LLM translation would have no trustworthy source baseline.

## Decision

ELMOS will use source-language semantic adapters, a future Unified Intermediate Representation (UIR), and target-language generators. The first gate is a language-neutral Repository Intake batch that generates no target source code.

`modules/intake` owns the framework-free Batch 1 contracts and orchestration:

1. immutable source identity and metadata-only file manifest;
2. evidence-backed mixed-language/project fingerprint;
3. format-aware Build Model;
4. source/resource inventory with model exclusions;
5. evidence-backed build dependency graph;
6. default-deny sandbox policy;
7. baseline result supplied only by an approved sandbox runner;
8. frozen `migration-manifest.yaml` and readiness gate.

Maven/MSBuild XML is parsed with external entities disabled, npm metadata as JSON, and Python metadata as TOML. Executable/opaque build descriptions such as Gradle DSL and `setup.py` are not evaluated during intake; unknown values stay `unresolved` until an approved sandbox/tooling export supplies evidence.

All artifacts are bound to the same `snapshotId`. The readiness score is informative; it cannot override a missing baseline or project model. `NOT_RUN` baseline evidence keeps the Batch 2 gate `BLOCKED`.

## Security consequences

- Intake does not run repository commands, lifecycle hooks or package managers.
- File contents are not present in output models; secret-like, binary and vendored files are explicitly excluded from model context.
- Git input requires a resolved commit and a credential-free remote representation.
- Baseline execution remains outside the control plane and must use the existing rootless, default-deny Workspace boundary.

## Scope boundary

Batch 1 build graph edges are exact descriptor-derived edges. Source imports, type resolution, calls and control flow belong to Batch 2 language adapters. Their absence is explicit `unresolved` evidence, never an invented empty graph.

## Consequences

The original Java/Spring modernization engine remains a supported specialized path. Later translation batches consume the unified manifest, which prevents language-pair code from bypassing snapshot, safety and baseline gates.
