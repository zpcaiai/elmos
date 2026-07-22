---
name: uir-serialization-and-query-index
description: Serialize, version, incrementally store, and index large UIR datasets. Use for artifacts, random access, graph queries, or snapshot coexistence.
---
# UIR Serialization and Query Index
Read `../references/uir-v1.md`. Write manifest, protocol/dialects, Zstandard JSONL entity streams, language extensions, reports, and rebuildable SQLite/graph indexes atomically. IDs, not order, define links. Preserve content hash, generation, supersedes and deletion markers for increments; never mutate old snapshots. Support declaration/body, type-use, def-use, effect, API call-chain, source-range, obligation, risk and module-order queries without loading all operations.
