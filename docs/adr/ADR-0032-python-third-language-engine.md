# ADR-0032: Python is a third execution engine with three validation paths

## Status

Accepted for Batch 12 on 2026-07-21.

## Context

Python modernization combines source syntax, dynamic runtime behavior, environment and native ABI state, data semantics, and executable model artifacts. A Web service, data pipeline, and AI/ML system can share a repository and dependencies while requiring materially different acceptance evidence. The Java control plane already owns tenant, authorization, workflow, Runner, Evidence, usage, audit, SCM, delivery, and rollback authority.

Python 3.14 is the current stable series while 3.15 remains a prerelease as of this decision. LibCST preserves formatting needed by auditable Codemods, while CPython AST provides syntax and semantic structure; neither static layer can prove dynamic paths by itself.

## Decision

Implement `engines/python-engine` as an independently deployable Python 3.14 Worker behind the shared Engine API. Route `PYTHON` through `LanguageEngineRouter`; do not link LibCST, type checkers, model frameworks, or customer modules into Java.

Combine safe static discovery, environment and lock evidence, LibCST, AST, explicit mypy/Pyright adapter contracts, bounded runtime-trace contracts, test evidence, and path-specific differential validation. Until a capability-matched Runner executes either dynamic adapter, its result remains `NOT_RUN`; runtime traces are executed-path evidence only.

Create distinct Web, Data Pipeline, and AI/ML profiles and gates. Route Python 2, modern CPU, GPU, Windows, and Notebook workloads to separate approved Runner capabilities. Never load executable model artifacts in the control plane or static scanner.

Reuse shared ELMOS portfolio and dependency edges for Java, .NET, and Python. Store Python details in versioned evidence extensions and V12 analysis tables without duplicating workflow, permission, billing, audit, SCM, or delivery tables.

## Consequences

- Import success is not migration success.
- Environment reproduction precedes dependency upgrades.
- `2to3` is a candidate-only legacy adapter, not the transformation authority.
- Web HTTP/session/database evidence cannot substitute for data or model evidence.
- Statistical similarity cannot replace an approved business invariant.
- Artifact, inference, and training verdicts stay separate.
- GPU, Windows, Legacy, Notebook, and executable-artifact evidence stays `NOT_RUN` until produced in an approved Runner.

## References

- [Python downloads](https://www.python.org/downloads/)
- [LibCST documentation](https://libcst.readthedocs.io/en/latest/)
- [pylock.toml specification](https://packaging.python.org/en/latest/specifications/pylock-toml/)
- [Django 6.0 release notes](https://docs.djangoproject.com/en/6.0/releases/6.0/)
