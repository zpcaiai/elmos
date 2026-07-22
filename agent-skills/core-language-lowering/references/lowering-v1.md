# Batch 5 Lowering Protocol v1

## Purpose

Lower eligible UIR callable bodies into the Batch 4 target skeleton in two phases: a deliberately explicit faithful implementation followed, only after successful static validation, by a reversible idiomatic rewrite. Static success means ready for later behavioral testing, never behaviorally equivalent.

## Required inputs

- Batch 3 UIR run, entities, effects, exceptions, async contracts, aliases, source maps and obligations.
- A Batch 4 target repository whose module gate permits body generation, target profile, manifest, declaration mappings and protected placeholders.
- Version-bound capability matrix, deterministic rule registry and approved dependency registry.
- Generation profile and hard budgets for rules, patch size and agent calls.

Reject mismatched run IDs, target declaration IDs, failed module gates, unresolved target versions, missing compiler/AST backends, changed base hashes or manual-region conflicts.

## Two-phase invariant

Phase A preserves type meaning, operand and argument order, effect count, short circuiting, exception timing/channel, numeric width/precision/overflow, collection order/mutability/laziness, absence distinctions, async boundaries, cancellation and cleanup. Prefer explicit temporaries and loops when they make those properties auditable.

Phase B runs only after Phase A parses, binds and type-checks. Batch 5 permits local Level 1/2 idioms by default. Each rewrite must preserve type, effects, evaluation order, exception and async contracts, collection profile and open obligations; otherwise retain the faithful body.

## Callable lifecycle

`planned -> lowering -> generated-faithful -> verified-faithful -> idiomatized -> verified`. Unsafe or incomplete cases become `agent-required`, `manual-required` or `blocked`; they never become empty bodies, null/default returns, swallowed exceptions, `any`/`dynamic` camouflage or suppressed diagnostics.

## Deterministic rules

Every automatic operation records one stable rule ID and version, strategy, fidelity, generated node IDs, obligations and confidence. Rank project, enterprise, framework, library, language and generic rules in that order. Resolve ties by specificity, satisfied preconditions, fidelity and priority. If equally ranked candidates remain, block instead of choosing randomly. Production rules must be tested and idempotent and cannot introduce unapproved dependencies.

## Target capabilities

Bind every capability fact to the target language and version. States are `native`, `native-with-constraints`, `desugar`, `helper`, `compatibility-runtime`, `wrapper`, `agent`, `manual`, or `unsupported`. Every non-native state needs a bounded fallback or explicit blocking condition. Treat JavaScript separately from TypeScript and exclude preview features unless approved.

## Safety invariants

- Unknown/Any/Dynamic/Object mappings cannot hide missing type information; lossy public API mappings block.
- Decimal does not become binary floating point; Python arbitrary integers need range or big-integer handling.
- Null, None, undefined, optional-empty, missing key/property and uninitialized remain distinguishable unless an evidenced obligation approves merging.
- Do not duplicate effectful getters/indexers/arguments, pre-evaluate lazy operands, reorder `await`, or move work across locks/finally/resource scopes.
- Preserve ordered/mutable/lazy/replayable collection properties and dictionary missing-key behavior; never add parallel execution automatically.
- Preserve generic constraints/variance/reification and closure capture mode, `this`, callback multiplicity and thread/event-loop contracts.
- Promise rejection remains an async fault channel; generators and async streams remain lazy and cancellable.
- Dynamic, reflection, eval, proxy and metaclass behavior use bounded adapters/allowlists or explicit escalation. Opaque nodes fail visibly with provenance and a blocking obligation.

## Emitter and validator boundary

The common emitter consumes a completed lowering plan and constructs target AST/LST/CST nodes; it does not decide business semantics. Use OpenRewrite/JavaParser for Java, Roslyn for C#, LibCST plus Python AST validation for Python, and TypeScript Factory/Printer/Program for TypeScript/JavaScript. Reparse formatted output and update source maps. A missing backend blocks the callable.

Validate syntax/version, symbol and overload binding, generic inference, assignments/returns/nullability/exhaustiveness/definite assignment, then compare effects, evaluation order, exception/async/collection/cleanup contracts and obligations. Preserve raw compiler diagnostics and link them to UIR operations. Do not suppress failures.

## Patch and provenance

Patch one callable at a time by AST symbol and stable Target Declaration ID inside its generated-body region. Check the base file hash. Replace placeholders or unchanged generated code; three-way merge generated modifications; never overwrite manual regions. A conflict produces a report, not a partial write. Every patch is atomic, reversible, idempotent and carries source operation IDs, rule IDs, obligations and before/after hashes.

## Escalation

Agent packets contain the callable, only necessary types and one/two-hop dependencies, UIR operations/effects/contracts, nearby target examples, locked public/evaluation/effect constraints, approved helpers, forbidden dependencies, obligations and exact validation commands. Accept only structured AST patches/diffs, rule proposals or unresolved reports. Reparse and type-check all candidates; high-risk financial, payment, authorization, transaction and concurrency code requires human review.

## Artifacts

Write deterministic artifacts under `lowering/`, operation/temporary/helper/agent mappings under `mappings/`, reversible patches under `patches/`, dimension-specific evidence under `reports/`, and separated logs under `logs/`. Keep method generation, deterministic/agent/manual/opaque status, static validation and source-map coverage separately measurable.

## Module gates

- L-A: generation >= 0.85, source maps >= 0.99, no untracked generated code.
- L-B: syntax >= 0.98, symbols >= 0.95, types >= 0.93, zero public signature regressions.
- L-C: deterministic plus verified agent >= 0.90 and no unstrategized blocking numeric/nullability/async obligation.
- L-D: generation >= 0.97, static validation >= 0.96, deterministic >= 0.90, opaque <= 0.01, manual <= 0.03, source maps >= 0.995.

Gate modules independently. Repository averages cannot mask critical failures. Static compilation never establishes behavioral equivalence, and placeholders never count as success.
