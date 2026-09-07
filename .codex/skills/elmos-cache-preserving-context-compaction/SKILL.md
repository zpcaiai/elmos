---
name: elmos-cache-preserving-context-compaction
description: Compact long coding sessions without destroying stable prompt-prefix reuse, provenance, task state, or repository correctness.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P9-context-runtime
dependencies: [elmos-append-only-repository-context-ledger, elmos-intermediate-artifact-manifest, elmos-checkpoint-resume]
---

# Cache-Preserving Context Compaction

## Outcome

Keep long-running ELMOS tasks below model context limits through deterministic checkpoints and layered summaries while minimizing cache resets. This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run reproducible verification, and attach evidence. A design document, mocked counter, or isolated demo is not completion.

## Use this skill when

- A multi-turn conversion or generation session approaches context limits.
- Conversation replay cost or latency grows despite high prefix reuse.
- ELMOS must resume after compaction, service restart, model migration, or provider TTL expiry.

## Required inputs

- Context ledger, current prompt segments, run/DAG state, repository snapshot, open decisions, tool observations, staged artifacts, and provider context limits.
- Compaction policy, token budgets, summary schemas, validation rules, and cache warmup strategy.
- Model/provider capability profile and exact cache accounting.

## Produced artifacts

- Hierarchical `ContextCheckpoint` containing task contract, repository state, decisions, unresolved issues, tool evidence, artifacts, and provenance.
- Deterministic compaction planner with soft/hard thresholds, protected segments, and cache-impact prediction.
- Summary validator and replay harness comparing uncompacted and compacted task behavior.
- Compaction event and cache warmup workflow with rollback to the prior checkpoint.
- Long-session SLO dashboard.

## Non-negotiable invariants

- Compaction never alters immutable stable system/safety/tool/schema segments within a compatibility group.
- No unresolved requirement, approval, failing test, changed file, pending side effect, or security constraint may be dropped.
- Every summary statement links to source ledger events or CAS artifacts and records freshness.
- Compaction is a planned boundary with a new prefix identity; it is not performed unpredictably on every turn.
- Provider-independent task state remains recoverable even if provider prompt cache is gone.
- Compacted state cannot be used to bypass exact file, artifact, build, or test validation.

## Execution workflow

1. Estimate future token growth and trigger soft planning before the provider hard context limit.
2. Freeze a consistent run/ledger snapshot and classify segments as immutable, retain verbatim, summarize, externalize to CAS, or drop as reproducible noise.
3. Generate and validate a structured checkpoint, then compile a new canonical prefix/session state.
4. Run a shadow continuation from both uncompacted and compacted states on deterministic tasks and compare decisions, edits, tools, and tests.
5. Warm the new prefix where supported, switch atomically, and retain the old checkpoint until rollback TTL expires.
6. Monitor post-compaction cache write/read ratio, quality, missing-context incidents, and total wall-clock savings.

## Implementation tasks

1. Define typed checkpoint sections for immutable task contract, repository/snapshot, read-context coverage, decisions, pending questions, DAG/node state, staged files, tests, errors, and safety controls.
2. Implement source-linked extractive summaries for critical facts and model-generated summaries only where validated against source events.
3. Externalize bulky tool outputs and files to CAS with digest references and on-demand retrieval.
4. Add a deterministic token estimator per provider/model and reserve budget for tool responses and repair loops.
5. Implement compaction compatibility IDs, old/new checkpoint linkage, transactional switchover, and rollback.
6. Create long-session benchmark scenarios with 100+ turns, repeated edits, model tool calls, failures, restart, and at least two compactions.
7. Add cache-aware compaction scheduling that prefers natural phase boundaries and avoids resetting a hot prefix immediately before high-volume turns.
8. Expose `COMPACTION_REQUIRED`, `COMPACTION_COMPLETED`, `CONTEXT_GAP`, and `COMPACTION_ROLLBACK` events.

## Acceptance criteria

- Long-session benchmark completes without context overflow or lost task state.
- After warmup turns following planned compaction, eligible cached-token reuse returns to at least 80%; steady pre-compaction phases retain the 90% target.
- Compacted and uncompacted deterministic continuations produce equivalent planned actions and pass the same build/test assertions.
- Zero unresolved requirements, stale warnings, approvals, side effects, or failing tests are omitted in the gold corpus.
- Rollback restores the prior checkpoint and ledger position without duplicate side effects.
- Compaction reduces total input-token processing and wall-clock cost versus an uncompacted control at equal task quality.

## Evidence required

- Checkpoint schema, planner/validator code, source-link coverage, and compaction compatibility records.
- Long-session replay reports for token usage, cache read/write, latency, task equivalence, and missing-context checks.
- Failure/restart/rollback traces and a sample explainable compaction manifest.
- Provider-specific context-limit and token-estimation compatibility matrix.

## Anti-patterns

- Blindly asking a model to summarize the conversation and deleting the source state.
- Compacting on every turn or at arbitrary token thresholds without considering cache reuse.
- Embedding large files or logs verbatim in the new stable prefix when CAS references suffice.
- Dropping failed tests, pending approvals, or user constraints because they are old.
- Treating provider prompt cache as the durable source of task state.

## Done condition

The skill is complete when deterministic, provenance-linked context checkpoints support long-session continuation, planned cache-aware switchover, equivalence tests, restart/rollback, and the package long-session SLOs.
