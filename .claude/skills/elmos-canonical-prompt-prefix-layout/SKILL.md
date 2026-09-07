---
name: elmos-canonical-prompt-prefix-layout
description: Build deterministic, cache-friendly prompt assembly that maximizes exact stable-prefix reuse while preserving policy, tool, schema, project, and task correctness.
version: 1.2.0
package: elmos-build-cache-staging-codex-claude-parity
phase: P8-parity-foundation
dependencies: [elmos-provider-prompt-cache-adapters, elmos-cache-key-fingerprinting, elmos-stage-contract-registry]
---

# Canonical Prompt Prefix Layout

## Outcome

Make prompt construction a versioned compiler pipeline whose stable prefix is reproducible, explainable, diffable, and intentionally separated from volatile task data. This is an implementation skill. The coding agent must inspect and modify the actual ELMOS repository, run reproducible verification, and attach evidence. A design document, mocked counter, or isolated demo is not completion.

## Use this skill when

- Prompt cache misses are caused by reordered tools, unstable JSON, timestamps, machine paths, dynamic environment data, or full-repository reinjection.
- Adding a system instruction, Skill, tool, output schema, repository summary, or model request template.
- Preparing ELMOS for Codex/Claude-class stable-conversation cache reuse.

## Required inputs

- Provider adapter capabilities and tokenization constraints.
- ELMOS system/safety policy, Skills, tool registry, output schemas, repository index, project summary, current task, diffs, and retrieved context.
- Canonical serialization and hashing functions already used by ActionKey logic.
- Prompt prefix schema, compatibility policy, and golden fixtures.

## Produced artifacts

- `PromptCompiler` with named immutable segments, deterministic ordering, canonical serialization, and explicit stability classes.
- `PromptPrefixManifest` containing segment digests, sizes/tokens, schema versions, cache breakpoints, compatibility group, and change explanation.
- Golden prompt fixtures and semantic-diff tooling that identifies the first changed byte/token and responsible segment.
- Provider-specific compiled requests produced from the same logical prompt IR.
- Lint rules that reject volatile fields in stable segments.

## Non-negotiable invariants

- The stable prefix contains only fields whose changes should legitimately invalidate reuse.
- Segment order is fixed: system policy, safety policy, stable tool definitions, output schemas, stable Skill context, repository architecture summary, then cache boundary; task/diff/retrieval/tool results follow the boundary.
- JSON, tool definitions, enums, and maps use canonical sorting and normalized Unicode, line endings, paths, numeric forms, and whitespace.
- Timestamps, random IDs, request IDs, temporary directories, host names, non-semantic environment values, and volatile counters are excluded from stable segments.
- A prefix change increments or derives a compatibility identity and emits a machine-readable reason.
- Optimizing cache layout cannot remove instructions needed for safety, authorization, correctness, or output validation.

## Execution workflow

1. Capture current prompt variants and use first-difference analysis to rank avoidable invalidators by lost cached-token value.
2. Define prompt IR segments and classify each as `GLOBAL_STABLE`, `PROJECT_STABLE`, `SESSION_APPEND_ONLY`, or `TURN_VOLATILE`.
3. Implement canonical compilers and golden fixtures before enabling provider cache hints.
4. Move volatile project/task data after the cache boundary without changing model-visible semantics.
5. Run byte-level, token-level, semantic, policy, and provider request snapshot tests.
6. Canary the new layout and compare eligible cached-token reuse, cache writes, first-token latency, answer quality, and tool correctness.

## Implementation tasks

1. Create a versioned Prompt IR and segment registry with ownership, stability class, digest, token estimate, sensitivity, and allowed provider mappings.
2. Canonicalize tool schemas, tool order, Skill order, output schemas, repository symbols, and architectural summaries.
3. Generate a stable `prompt_cache_key`/routing identity from provider namespace plus compatibility group rather than from volatile turn data.
4. Add a prefix-diff command that prints segment-level and first-byte/token changes without exposing secrets.
5. Add a linter for timestamps, UUIDs, absolute paths, nondeterministic map iteration, mutable file lists, and environment leakage in stable segments.
6. Add compatibility tests proving that harmless whitespace/path-order changes do not alter the semantic prefix digest while real policy/tool/schema changes do.
7. Record per-segment token contribution and prioritize high-token stable segments for breakpoints where supported.
8. Implement a migration mode that can warm the new prefix while the old layout remains available for rollback.

## Acceptance criteria

- One logical stable prompt compiles byte-identically across repeated processes and supported operating systems.
- Reordering input maps, filesystem enumeration, or equivalent JSON does not change the canonical stable-prefix digest.
- Changing safety policy, model, effort, tool schema, output schema, or materially different repository architecture changes the correct compatibility identity.
- The fixed benchmark corpus shows at least 90% eligible cached-token reuse after turn 3, or the build fails with a segment-level miss report.
- Unexpected full-prefix misses are at most 2% in the stable-conversation benchmark.
- No policy, authorization, tool, or output-validation regression is accepted for a cache gain.

## Evidence required

- Prompt IR schema, compiler source, prefix manifests, golden fixture digests, and compatibility table.
- First-difference report for before/after prompt layouts and top invalidation causes removed.
- Benchmark token accounting, latency, quality/tool-use regression results, and provider observations.
- Lint output showing zero unapproved volatile fields in stable segments.

## Anti-patterns

- Reordering system instructions or tools on every request.
- Embedding current time, run ID, working directory, full dynamic file list, or tool results before the cache boundary.
- Using a semantic hash to claim exact provider prefix identity.
- Packing all context into one opaque string that cannot explain invalidation.
- Saving tokens by omitting safety or correctness instructions.

## Done condition

The skill is done when deterministic prompt compilation, manifests, lints, golden tests, provider mappings, cache-preserving migration, and parity benchmark evidence are integrated and the stable-prefix SLO gates pass.
