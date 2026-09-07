---
name: polyglot-semantic-protocol-emitter
description: Emit stable, versioned, streaming PSP v1 semantic artifacts and indexes from Batch 2 entities. Use when packaging language-adapter results for audit, query, caching, conformance, or Batch 3 UIR input.
---

# Polyglot Semantic Protocol Emitter

Read `../references/psp-v1.md` before acting.

Validate and deterministically sort envelopes, then atomically write the PSP artifact layout as JSON/JSONL+Zstandard and a SQLite entity/relation/source-range index. Common facts stay in the core envelope; native facts stay in ignorable language extensions. Include protocol/source-position/ID algorithm versions, run manifest, coverage, diagnostics, and reports.

Every entity requires protocol, entity, snapshot, run, project, language, payload, and provenance fields. JSONL order must not carry meaning; references resolve through IDs/indexes. Optional additions are minor-version compatible; removing fields or changing field/ID/range/resolution semantics requires a major version. Never emit source text, credentials, or an entity without provenance.
