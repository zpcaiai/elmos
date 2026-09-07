# Merge Guide

This package is designed to be merged into an existing Elmos skills repository without replacing existing domain packs.

## 1. Keep existing Golden Routes
Do not rename existing Spring modernization, polyglot conversion, project generation or SQL route skills. Add these cross-cutting skills as dependencies/certification requirements.

## 2. Add normalized contracts first
Merge `schemas/`, `architecture/` and K1/K6 contracts before wiring every tool. This prevents tool-specific APIs from leaking into domain skills.

## 3. Recommended implementation order
- Wave A (P0 foundation): K1 runtime + K2 code graph + K4 sandbox/hermetic + K6 policy/provenance.
- Wave B (P0 correctness): K3 rewrite router + K5 differential/fuzz/static/contract + K7 database compiler.
- Wave C (P0 operations): K8 tracing/eval/cost + affected-test/remote cache/native runtime lab.
- Wave D (P1): formal router, self-evolution, chaos, software catalog, progressive rollout.

## 4. Domain skill dependency pattern
A domain migration skill should declare dependencies such as:
`repository-semantic-code-graph -> change-risk-classifier -> multi-engine-rewrite-router -> hermetic-build-environment -> evidence-gate-orchestrator -> slsa-in-toto-provenance`.

## 5. Do not over-couple upstreams
Define interfaces such as `ParserProvider`, `SymbolIndexer`, `RewriteEngine`, `SandboxProvider`, `PolicyEngine`, `EvidenceEmitter`, `BuildExecutor`, `FuzzProvider`. Upstream projects should be adapters behind these interfaces.
