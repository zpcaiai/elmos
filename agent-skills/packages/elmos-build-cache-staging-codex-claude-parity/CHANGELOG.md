# Changelog

## 1.2.0 — 2026-08-20

### Added

- 11 Skills for provider prompt caching, canonical prefix construction, append-only repository context, cache-preserving compaction, environment snapshots, cache affinity, multi-layer coordination, miss diagnostics, parity benchmarking, SLO autotuning, and end-to-end rollout.
- Hard parity gates for cached-token reuse, exact reruns, small edits, environment warm starts, restart recovery, wall-clock/model-cost savings, and zero false hits.
- 9 new JSON Schemas, parity configuration and manifests, OpenAPI supplement, PostgreSQL migration sketch, 4 ADRs, official mechanism research note, and parity acceptance matrix.
- Reference Python modules and 14 new unit tests; total reference suite is 34 tests.
- Example parity evaluator with 15 mandatory checks.

### Changed

- Package ID is now `elmos-build-cache-staging-codex-claude-parity`.
- Package version is 1.2.0 and final entry Skill is `elmos-codex-claude-cache-parity-rollout`.
- All 31 v1.1.0 Skills were retained and frontmatter was upgraded to the new package identity.
- Validation now enforces 42 Skills, 34 tests, parity-gate execution, installer smoke testing, entry identity, and checksum integrity.

### Compatibility

Existing CAS objects and Action Cache entries are reusable only when their exact identities, validation levels, tenancy, provenance, and schema compatibility remain valid. Provider prompt-prefix and environment snapshot caches use new versioned namespaces. See `MIGRATION-v1.1-to-v1.2.md`.
