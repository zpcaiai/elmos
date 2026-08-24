---
name: elmos-append-only-repository-context-ledger
description: Persist repository reads, summaries, diffs, stale markers, and tool observations as an append-only context ledger so unchanged conversation prefixes remain reusable across coding turns.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P9-context-runtime
dependencies: [elmos-canonical-prompt-prefix-layout, elmos-project-snapshot-merkle, elmos-semantic-interface-hashing, elmos-run-journal-state-machine]
---

# Append-Only Repository Context Ledger

## Outcome

Replace repeated whole-repository prompt injection with provenance-linked, on-demand context acquisition and append-only change events. This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run reproducible verification, and attach evidence. A design document, mocked counter, or isolated demo is not completion.

## Use this skill when

- ELMOS performs multi-turn repository generation, conversion, repair, review, or testing.
- Files change after being read, long sessions repeatedly resend the repository, or context becomes stale without traceability.
- Prompt reuse must survive ordinary edits while the model still sees accurate current-state warnings.

## Required inputs

- Repository snapshots, Merkle nodes, symbol/public-interface hashes, Git diffs, file-read events, tool results, and task/session identity.
- Prompt IR and cache boundary rules.
- Authorization and redaction policy for source content and summaries.
- Ledger event schema, compaction rules, and retention policy.

## Produced artifacts

- Append-only `RepositoryContextLedger` with hash-chained sequence numbers and optimistic concurrency.
- Events for snapshot attachment, file/symbol read, summary creation, file change, staleness, reread, tool result, validation result, and checkpoint.
- Context materializer that selects the minimum current evidence for a turn without rewriting prior conversation entries.
- Ledger-to-prompt projection, stale-context warnings, and repository coverage report.
- Recovery, replay, branch/fork, and concurrent-writer tests.

## Non-negotiable invariants

- Committed ledger events are immutable; corrections append superseding events rather than rewriting history.
- Every file/symbol observation binds to repository snapshot digest, content digest, path identity, and authorization context.
- When a previously read file changes, ELMOS appends a stale marker and rereads on demand; it does not mutate the old provider-cached prefix.
- Ledger materialization never presents stale content as current without an explicit warning and provenance.
- Branch, tenant, repository, and session boundaries are enforced in storage and retrieval.
- The ledger is not a hidden semantic cache that bypasses compilation, tests, or exact ActionKey validation.

## Execution workflow

1. Instrument file reads, symbol queries, repository searches, edits, builds, tests, and tool calls to produce ledger events.
2. Build deterministic projections for current task, changed files, relevant symbols, unresolved warnings, and recent tool evidence.
3. Add snapshot-diff processing that marks only affected observations stale using file and public-interface hashes.
4. Integrate the projection after the stable prompt prefix and preserve append-only conversation growth.
5. Exercise crash recovery, duplicate events, out-of-order delivery, concurrent edits, branch switches, and repository rebases.
6. Measure repository bytes/tokens avoided, reread precision, stale-context incidents, and stable-prefix reuse.

## Implementation tasks

1. Define event IDs, stream IDs, sequence/epoch rules, hash chain, idempotency keys, supersession links, and transactional outbox integration.
2. Implement event types `SNAPSHOT_BOUND`, `FILE_READ`, `SYMBOL_READ`, `SUMMARY_WRITTEN`, `CONTENT_CHANGED`, `CONTEXT_STALE`, `CONTENT_REREAD`, `TOOL_OBSERVED`, and `CONTEXT_CHECKPOINT`.
3. Create an inverted index from file/symbol digest to ledger observations for precise invalidation.
4. Implement a relevance projector constrained by token budget, freshness, task dependency graph, and security scope.
5. Append compact change notices instead of reinserting unchanged file contents; fetch changed content only when required.
6. Provide branch/fork/merge semantics and reject use of an event from an incompatible repository lineage.
7. Expose ledger lag, stale-item count, reread count, avoided tokens, and context source citations to tracing.
8. Add export/import fixtures with content redaction and deterministic replay.

## Acceptance criteria

- Replaying a ledger yields the same materialized context and digest for the same snapshot/task/profile.
- Editing an unread unrelated file does not invalidate prior read context or stable prompt segments.
- Editing a read file appends a stale marker before the next model request and never silently serves the old content as current.
- For the small-edit benchmark, whole-repository reinjection events are zero after initial indexing.
- Context selection precision/recall meets the package benchmark thresholds and stale-context false negatives are zero in deterministic fixtures.
- Crash recovery and duplicate delivery preserve exactly-once logical event semantics.

## Evidence required

- Ledger schema/migrations, event processor, projection code, hash-chain verification, and recovery tests.
- Before/after prompt traces showing avoided repository reinjection and preserved exact prefix.
- Stale-file mutation tests, branch isolation tests, token savings, and context-quality measurements.
- Operator query examples for explaining why a file or summary was included.

## Anti-patterns

- Replacing or editing old conversation messages when repository files change.
- Injecting every repository file into every turn to avoid building retrieval logic.
- Using summaries without snapshot/content provenance or freshness state.
- Silently accepting out-of-order or cross-branch events.
- Logging source content or secrets in high-cardinality event metadata.

## Done condition

Completion requires a durable append-only ledger, deterministic context projection, precise staleness propagation, crash/branch/isolation tests, prompt integration, observability, and benchmark evidence showing no whole-repository reinjection on follow-up turns.
