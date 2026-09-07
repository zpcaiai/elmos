# ADR-0007: Preserve repository context as an append-only ledger

Status: accepted

## Decision

File reads, summaries, edits, staleness, tool observations, and checkpoints are immutable hash-linked events. Changed files append stale/reread events instead of rewriting prior conversation content. Whole-repository reinjection is disallowed after initial indexing.

## Consequences

- Stable provider prefixes survive ordinary edits.
- Every context item has snapshot/content provenance and freshness.
- Recovery and compaction are provider-independent.
- Storage and projection complexity increase, but hidden stale context is testable.
