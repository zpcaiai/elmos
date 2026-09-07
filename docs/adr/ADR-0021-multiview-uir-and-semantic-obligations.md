# ADR-0021: Multi-view UIR and semantic obligations

- Status: Accepted
- Date: 2026-07-21

## Decision

Batch 3 uses a versioned dialect-based semantic superset with linked high-level declarations/types (UIR-H), structured execution (UIR-S), and derived CFG/SSA/effect analysis (UIR-C). SSA is not the generation representation. PSP modules must pass their module gate before lifting. Native differences in absence, numeric behavior, evaluation order, exception/rejection, async/concurrency, effects, mutability/alias, dynamic/reflection and language-specific constructs are retained rather than collapsed.

`modules/uir` owns deterministic lifting, dialect verification, source/transformation provenance, opaque/unknown preservation, semantic obligations, per-module UIR gates, Zstandard artifacts and rebuildable SQLite indexes. Missing executable semantics become mapped opaque operations with unknown effects and verification strategies; no business behavior is invented.

PSP v1 call sites and control-flow summaries are partial semantic evidence, not a complete executable body. Until an authority adapter emits complete operation-level body evidence, the lifter retains an opaque body remainder and an open blocking obligation. That representation can qualify for skeleton generation at UIR-B, but the presence of resolved call sites alone cannot qualify it for automatic translation.

Batch 3 generates no target source. Batch 4 requires UIR-B; automatic translation requires stricter gates.
