# AGENTS.md — ELMOS Cache, Staging, SOTA, and Coding-Agent Cache Parity

## Mission

Implement a production-grade, evidence-backed subsystem in the actual ELMOS repository. The Skills package is an executable specification, not proof that production integration or parity already exists.

## Mandatory reading order

1. `README.md` or `README.zh-CN.md`
2. `manifest.json`
3. `docs/source-packages/elmos-build-cache-staging-spec.md`
4. `docs/source-packages/elmos-sota-cache-optimization-spec.md`
5. `docs/source-packages/elmos-codex-claude-cache-parity-spec.md`
6. `docs/research/official-coding-agent-cache-mechanisms.md`
7. The selected Skill and every dependency Skill
8. Relevant schemas, SQL, OpenAPI, templates, ADRs, and acceptance rows

## Execution rules

- Inspect the actual ELMOS repository before choosing modules, tables, frameworks, providers, or deployment boundaries.
- Preserve immutable bytes in CAS and durable mutable orchestration state in PostgreSQL/SQLite; Redis is never the only recoverable truth.
- Never write generated content directly into source or final output. Preserve the staged-file lifecycle and atomic complete-tree publication.
- Exact Action Cache, provider prompt-prefix reuse, environment snapshots, native build cache, and semantic reuse are distinct layers.
- Provider prompt-cache reads reduce input-prefix processing; they do not make model outputs exact, validated, or publishable.
- Canonically order stable prompt segments and keep timestamps, random IDs, temporary paths, host data, dynamic diffs, retrieval results, and tool output after the boundary.
- Preserve repository context as append-only events. Changed files append stale/reread events; do not rewrite old prompt history.
- Keep durable task state in run journal/checkpoints/CAS/staging, not solely in a provider cache, model conversation, local memory, or one worker.
- Environment snapshot keys must include every result-affecting image/script/lockfile/toolchain/platform/approved-environment input. Never bake secret values into layers.
- Treat authorization, compatibility, health, capacity, and trust as hard routing filters; locality is a soft preference with fairness and overload escape.
- Use Singleflight only for identical authorized work. Preserve cancellation, deadlines, and independent result delivery.
- Every cache outcome must have an evidence-derived reason. `UNKNOWN` consumes the unexpected-miss budget.
- Optimize avoided compute, model tokens/cost, critical path, wall clock, bytes, and validation work—not raw hit count alone.
- Learned/adaptive control never changes ActionKey semantics, digest verification, tenancy, authorization, validation level, staging, or publication correctness.
- Prefer a correct miss to a false hit. Any false/cross-tenant/corrupt/under-validated hit blocks certification and triggers rollback.
- Never claim universal Codex/Claude equivalence. State workload, eligibility, provider/model/tool profile, date, corpus, and measured result.

## Required evidence

- Source commit or explicit working-tree diff and configuration digest.
- Exact commands, full pass/fail counts, provider/SDK/model profiles, and platform metadata.
- Prompt Prefix Manifests, first-difference miss examples, ActionKey/invalidation examples, environment snapshot manifests, and affinity decisions.
- Cold/warm/ablation parity report with raw usage observations and reconciled unified attribution.
- Security, cross-tenant, corruption, chaos, restart, compaction, migration, and rollback traces.
- Explicit limitations and unsupported/cold-start boundaries.

## Definition of done

Implementation code, migrations, adapters, tests, telemetry, feature flags, runbooks, SLOs, rollback, fresh parity certificate, and the ELMOS repository’s own verification must all pass. Package `./validate.sh` proves package consistency only.
