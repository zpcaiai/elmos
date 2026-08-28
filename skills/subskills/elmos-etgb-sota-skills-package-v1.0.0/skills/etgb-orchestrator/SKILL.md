---
name: etgb-orchestrator
description: Plan, execute, resume, aggregate, and certify Elmos ETGB test runs across all four business lines.
---

# ETGB Orchestrator

## Purpose

Use this Skill whenever a model, rule, migration engine, generator, SQL converter, harness, cache or deployment candidate must be evaluated against ETGB. It owns test planning and lifecycle, but does not own product transformation logic or hidden-test content.

## Inputs

- immutable release candidate: model, prompt, Skill, rule, toolchain and image digests;
- business line and source/target path;
- changed files or selected capability IDs;
- run profile and budget;
- corpus lock and environment policy;
- tenant/project/task identity.

Reject mutable model aliases, unpinned toolchains or missing environment ownership for release/golden profiles.

## Outputs

- immutable run plan and shards;
- case execution records;
- Oracle results and evidence references;
- coverage, cost and wall-clock report;
- release gate decision or explicit blocked/unavailable reason.

## Invariants

1. Generation/translation workers cannot read or modify hidden tests.
2. A skipped or unavailable case is never counted as passed.
3. Product failures are not retried until green; only classified infrastructure failures may receive one diagnostic retry.
4. Every side effect uses idempotency key, ownership and fencing token.
5. Resume uses persisted checkpoints and verifies artifact digests.
6. Success claims require complete evidence.

## Workflow

### 1. Resolve scope

Read `matrices/coverage-requirements.yaml`, the release candidate and changed-path map. Select:

- smoke always;
- affected P0 for PR;
- full profile set for nightly/weekly/release/golden;
- historical incident cases matching changed components;
- random unaffected control sample.

Produce case IDs before execution; do not dynamically hide failures by changing scope.

### 2. Validate preconditions

- run `etgb validate` and `etgb coverage`;
- confirm corpus commits and license status;
- provision isolated environments;
- verify secrets, network, resource and retention policies;
- reserve token/credit and compute budget;
- persist plan digest and ownership.

### 3. Shard

Use stable key `case_id + corpus_commit + candidate_digest + seed`. Respect account concurrency and global fairness. Keep all seeds of a case logically grouped for final statistics.

### 4. Execute phase machine

```text
PLANNED → PREPARING → BASELINING → TRANSFORMING/GENERATING
→ BUILDING → VALIDATING → SCORING → PUBLISHING → COMPLETED
```

Every transition is compare-and-set with fencing. Cancellation or failure enters a compensating state, not an implicit success.

### 5. Invoke domain Skill

Route by `business_line` to the Spring, repository translation, project generation or SQL Skill. Invoke `differential-oracle-engine` for source/target comparison and `metamorphic-fuzz-mutation` according to profile.

### 6. Aggregate

Do not average away P0 failures. Report per line, pair/archetype/stack, capability, Oracle, seed, model and failure class. Compute SSER, HIR, weighted pass, flake, cost and wall-clock.

### 7. Certify

Call `release-certification`. A complete run is promotable only when all hard gates pass. Persist signed evidence and decision.

## Failure handling

- Environment unavailable: mark `unavailable`, record missing capability.
- Source baseline broken: classify separately; do not blame translation.
- Oracle conflict: quarantine result for Oracle review; never auto-select a favorable Oracle.
- Budget exceeded: stop at safe checkpoint, finalize incurred cost and mark incomplete.
- Ownership lost: terminate tool access and refuse further publication.

## Commands

```bash
etgb validate
etgb coverage
etgb plan --changed-from origin/main --output reports/plan.json
etgb run --plan reports/plan.json --output reports/results.jsonl --allow-unavailable
etgb score reports/results.jsonl --output reports/score.json
```
