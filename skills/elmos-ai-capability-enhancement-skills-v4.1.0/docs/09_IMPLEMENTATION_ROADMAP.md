# Implementation Roadmap

The package contains 12 ordered batches and 120 implementation tasks in `implementation/batches.yaml`. Each task is an instruction to modify the real Elmos repository and produce current evidence; it is not satisfied by copying this package.

## Critical path

```text
B00 V3 integration
  ↓
B01 AI-SIR
  ↓
B02 Adapter SDK
  ↓
B03 P0 application generators ─┐
B04 Harness generators ────────┼─► B06 durable runtime
B05 Agent ecosystems ──────────┘        ↓
                                  B07 proof/verification
                                         ↓
                                  B08 upgrade/lifecycle
                                         ↓
                                  B09 Golden Routes
                                         ↓
                                  B10 scale/operations
                                         ↓
                                  B11 commercial E5
```

Parallel work is possible inside batches only where API/schema and canonical ownership are frozen.

## B00 — V3 integration and ownership

Deliver:

- non-routable Domain Pack extension registration;
- no new Goal/semantic/runtime/certificate truth source;
- package feature flags and schema/evidence registries;
- database/API migration plan;
- CI validators and safe installer;
- architecture decision records.

Exit only when the existing 16 v3 routes remain stable and all 75 components map to the `project-generation` owner and K1–K8.

## B01 — AI-SIR

Build the actual compiler/model packages, persistence and APIs for all 11 semantic domains. Use typed schema migrations, stable semantic IDs, source maps, provenance, gap obligations and incremental compilation.

Minimum vertical slice:

```text
business requirement
 → solution/model/agent/workflow/tool/security/runtime/assurance contracts
 → valid AI-SIR
 → one target capability negotiation
 → proof obligation seed
```

## B02 — Adapter SDK

Build a real plugin interface and target-worker protocol. The reference adapter should:

- import a small source project;
- profile an exact target version;
- lower AI-SIR;
- emit a repository;
- invoke the target's official build/load command;
- publish evidence;
- detect a breaking upstream change.

No P0 target work should bypass this SDK.

## B03 — P0 application generators

Recommended internal order:

1. Universal RAG vertical slice.
2. LangGraph Python production runtime.
3. Spring AI Java enterprise service.
4. Dify prototype/import/round trip.
5. LangChain import/compatibility.
6. TypeScript variants.

The first commercially meaningful vertical route is:

```text
contract assistant requirement
 → Dify prototype
 → LangGraph service
 → Spring AI service facade
 → shared RAG data/evals
 → cross-target trace and grounding evidence
```

## B04 — Harness and OpenClaw

Generate repository-specific packages rather than generic `SKILL.md` files:

- exact build/test/format commands;
- architecture/repository maps;
- allowed tools/paths/network;
- worktree and Git policy;
- checkpoint/recovery;
- proof-of-work and review;
- task benchmarks;
- host-native loading.

OpenClaw deployments use gateway/tenant isolation and signed/allowlisted plugins.

## B05 — Agent ecosystems

Implement P0 adapters against official sample projects and upstream tests where licenses permit. Keep feature matrices versioned. AutoGen/Semantic Kernel/Flowise/Swarm are importer/migration profiles unless product policy promotes them.

## B06 — Runtime

The earliest production runtime must demonstrate:

- a run survives process and worker loss;
- stale worker commits are rejected;
- pause/resume/cancel is deterministic;
- external-write reconciliation handles crash ambiguity;
- two tenants cannot access state, vector data, cache, trace or evidence;
- per-account concurrency and budget enforcement work;
- machine ETA and cost are persisted.

## B07 — Verification

Implement normalized trace schema first, then:

- target-native conformance;
- source/target differential;
- RAG evaluation;
- graph/state/side-effect checks;
- injection and authority red team;
- supply chain;
- performance/resilience;
- independent K8.

A generated project that only compiles remains E2.

## B08 — Upgrade

Treat generated systems as maintained products:

- upstream release watcher;
- compatibility impact;
- AI-SIR migration;
- user-owned region preservation;
- selective regeneration;
- evidence invalidation;
- certificate renewal/revocation.

A full destructive re-generation is not an upgrade strategy.

## B09 — Golden Routes

Each route needs:

- eligibility and exclusion criteria;
- at least three independent repetitions;
- holdout scenarios not authored by the generating model;
- exact machine wall-clock and cost;
- failure/recovery and rollback;
- upgrade drift;
- customer acceptance;
- sealed evidence and a bounded certificate.

Start with one paid Spring/LangGraph/RAG route before broad catalog marketing.

## B10 — Scale

Scale dimensions:

- repository/file/symbol/AI-SIR node count;
- number of targets;
- concurrent tenants/runs;
- model/tool calls;
- data/document/index size;
- trace/evidence volume;
- verifier matrix;
- recovery and upgrade workload.

Measure incremental reanalysis and cache validity, not only raw throughput.

## B11 — Commercial E5

E5 includes the software plus operating organization:

- security/privacy review;
- support, on-call and escalation;
- compatibility and deprecation policy;
- signed release and supply-chain controls;
- backup/restore/RTO/RPO;
- billing/credits and dispute evidence;
- enterprise identity/audit;
- customer VPC/private deployments;
- pilot and rollback exercise;
- independent release authority.

## Definition of package implementation

The package is implemented in Elmos only when the target repository contains working services, schemas, migrations, adapters and tests and has current evidence. File count, generated scaffolds, or this package's validator are not implementation evidence.
