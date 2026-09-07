# ADR-0020: Polyglot Semantic Protocol and authority-bound adapters

- Status: Accepted
- Date: 2026-07-21

## Context

Batch 1 provides immutable repository identity, build projects, source roots, dependencies, exclusions, and baseline evidence. Batch 2 must understand Java, Python, C#, and JavaScript/TypeScript without reducing native compiler semantics to a lowest-common-denominator AST or asking a model to guess bindings.

## Decision

ELMOS defines Polyglot Semantic Protocol v1 (PSP v1) with three linked layers: lossless tokens/CST and trivia; language-native semantic facts; and a common versioned envelope with language extensions. Every fact carries snapshot/run/project identity, deterministic ID, provider/version/method, resolution level, confidence, input hashes, and source evidence.

`modules/semantic` owns the framework-free orchestration, contracts, deterministic identifiers, UTF-8 source ranges, authority adapter boundary, syntax fallback, integrity/coverage validator, Zstandard JSONL emitter, reports, and rebuildable SQLite index.

Authoritative semantics may come only from pinned allowlisted providers through the isolated engine/workspace port: JDT/Javac/JavaParser/OpenRewrite for Java, LibCST plus Pyright for Python, Roslyn for C#, and the TypeScript Compiler API plus Babel for JavaScript/TypeScript. A Tree-sitter-compatible fallback can preserve source structure, but emits a blocking diagnostic and cannot qualify a module for Batch 3.

## Gates

Conformance is evaluated per module. Gate A requires syntax parse rate 0.98, source-map coverage 0.99, and symbol resolution 0.90 by default. Gate B additionally requires type resolution 0.85, unresolved calls at most 0.10, and no blocking diagnostic. Gate C raises automation thresholds. Dynamic-language thresholds may be explicitly profiled, but ambiguity remains dynamic/candidate/unresolved evidence.

## Security and scope

The control plane does not execute repository code, imports, lifecycle scripts, annotation processors, source generators, JavaScript modules, or unknown Roslyn analyzers. Batch 2 generates no target project or source code. Artifact indexes are derived and rebuildable; versioned JSON/JSONL artifacts are the source of truth.

## Consequences

Batch 3 can consume a stable, queryable semantic substrate and select eligible modules independently. Environments without the native authority workers still receive useful lossless diagnostics, but cannot silently advance to UIR or translation.
