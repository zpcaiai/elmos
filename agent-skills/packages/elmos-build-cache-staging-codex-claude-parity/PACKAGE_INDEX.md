# Package Index

Package: `elmos-build-cache-staging-codex-claude-parity` v1.2.0

Total skills: **42**

Entry skill: `elmos-codex-claude-cache-parity-rollout`

## Dependency execution order

1. `elmos-cache-system-architecture` — ELMOS Cache System Architecture
2. `elmos-cache-metadata-database` — Cache Metadata Database
3. `elmos-cache-api-cli-contracts` — Cache API and CLI Contracts
4. `elmos-project-snapshot-merkle` — Project Snapshot and Merkle Tree
5. `elmos-content-addressable-storage` — Content Addressable Storage
6. `elmos-cache-key-fingerprinting` — ActionKey and Stage Fingerprinting
7. `elmos-action-cache` — Action Cache
8. `elmos-project-generation-file-staging` — Project Generation File Staging
9. `elmos-atomic-file-write-promotion` — Atomic File Write and Promotion
10. `elmos-sandbox-overlay-workspaces` — Sandbox and Overlay Workspaces
11. `elmos-intermediate-artifact-manifest` — Intermediate Artifact Manifest
12. `elmos-stage-contract-registry` — Stage Contract Registry
13. `elmos-semantic-interface-hashing` — Semantic and Public Interface Hashing
14. `elmos-incremental-conversion-dag` — Incremental Conversion DAG
15. `elmos-run-journal-state-machine` — Run Journal and State Machine
16. `elmos-checkpoint-resume` — Checkpoint and Resume
17. `elmos-generation-conflict-merge` — Generation Conflict and Merge
18. `elmos-remote-shared-cache` — Remote Shared Cache
19. `elmos-native-build-cache-adapters` — Native Build Cache Adapters
20. `elmos-cache-security-provenance` — Cache Security and Provenance
21. `elmos-cache-retention-gc` — Cache Retention and Garbage Collection
22. `elmos-cache-observability-performance` — Cache Observability and Performance
23. `elmos-cache-chaos-certification` — Chaos Testing and Production Certification
24. `elmos-cache-trace-replay-simulator` — Cache Trace Capture and Replay Simulator
25. `elmos-sota-cache-policy-portfolio` — SOTA Cache Policy Portfolio
26. `elmos-dag-aware-cache-prefetch` — DAG-Aware Future-Reuse Prefetch and Placement
27. `elmos-cost-aware-cache-admission` — Cost-Aware Admission, Retention, and Eviction
28. `elmos-adaptive-cache-policy-orchestrator` — Adaptive Cache Policy Orchestrator
29. `elmos-learning-augmented-cache-control` — Learning-Augmented Cache Control Plane
30. `elmos-cache-autotuning-certification` — Cache Autotuning and Production Certification
31. `elmos-cache-rollout-end-to-end` — Rollout and End-to-End Integration
32. `elmos-provider-prompt-cache-adapters` — Provider Prompt Cache Adapters
33. `elmos-canonical-prompt-prefix-layout` — Canonical Prompt Prefix Layout
34. `elmos-append-only-repository-context-ledger` — Append-Only Repository Context Ledger
35. `elmos-cache-preserving-context-compaction` — Cache-Preserving Context Compaction
36. `elmos-environment-snapshot-cache` — Environment Snapshot Cache
37. `elmos-cache-affinity-routing` — Cache Affinity Routing
38. `elmos-multi-layer-cache-coordinator` — Multi-Layer Cache Coordinator
39. `elmos-cache-miss-diagnostics` — Cache Miss Diagnostics and Invalidation Explainability
40. `elmos-codex-claude-parity-benchmark` — Codex/Claude-Class Cache Parity Benchmark
41. `elmos-cache-hit-slo-autotuning` — Cache Hit SLO Autotuning and Regression Control
42. `elmos-codex-claude-cache-parity-rollout` — Codex/Claude-Class Cache Parity End-to-End Rollout

## Skills by phase

### P0-foundation

- `elmos-cache-system-architecture` — ELMOS Cache System Architecture  
  Dependencies: none
  Purpose: Define the authoritative architecture for deterministic build caching, durable generated-file staging, checkpointing, recovery, and evidence-backed publication across the ELMOS conversion pipeline.
- `elmos-cache-metadata-database` — Cache Metadata Database  
  Dependencies: `elmos-cache-system-architecture`
  Purpose: Implement transactional metadata for projects, snapshots, runs, nodes, artifacts, Action Cache entries, staged files, checkpoints, leases, references, events, and outbox jobs.
- `elmos-cache-api-cli-contracts` — Cache API and CLI Contracts  
  Dependencies: `elmos-cache-system-architecture`, `elmos-cache-metadata-database`
  Purpose: Define stable APIs and commands for cache lookup, blob transfer, workspace lifecycle, staged-file transitions, checkpoints, run recovery, diagnostics, and administration.

### P1-local-cache

- `elmos-project-snapshot-merkle` — Project Snapshot and Merkle Tree  
  Dependencies: `elmos-cache-system-architecture`
  Purpose: Create deterministic repository snapshots and Merkle trees so small changes invalidate only affected modules, files, symbols, and downstream actions.
- `elmos-content-addressable-storage` — Content Addressable Storage  
  Dependencies: `elmos-cache-system-architecture`, `elmos-cache-metadata-database`
  Purpose: Implement immutable, deduplicated, integrity-checked storage for AST, Semantic IR, mapping plans, generated files, patches, build outputs, tests, checkpoints, logs, and evidence bundles.
- `elmos-cache-key-fingerprinting` — ActionKey and Stage Fingerprinting  
  Dependencies: `elmos-project-snapshot-merkle`, `elmos-cache-system-architecture`
  Purpose: Build canonical, explainable cache keys that include every result-affecting input while excluding irrelevant machine-specific noise.
- `elmos-action-cache` — Action Cache  
  Dependencies: `elmos-content-addressable-storage`, `elmos-cache-key-fingerprinting`, `elmos-cache-metadata-database`
  Purpose: Map deterministic ActionKeys to immutable ActionResult manifests, diagnostics, resource usage, provenance, and validation levels.

### P2-staging

- `elmos-project-generation-file-staging` — Project Generation File Staging  
  Dependencies: `elmos-cache-system-architecture`, `elmos-cache-metadata-database`, `elmos-content-addressable-storage`
  Purpose: Provide a durable, recoverable workspace and explicit lifecycle for every file created while ELMOS generates a converted project, including fragments, patches, source maps, manifests, compiler outputs, and final publish candidates.
- `elmos-atomic-file-write-promotion` — Atomic File Write and Promotion  
  Dependencies: `elmos-project-generation-file-staging`, `elmos-content-addressable-storage`
  Purpose: Implement crash-safe writes, sealing, CAS promotion, complete-tree assembly, atomic publication, and rollback.
- `elmos-sandbox-overlay-workspaces` — Sandbox and Overlay Workspaces  
  Dependencies: `elmos-project-generation-file-staging`, `elmos-atomic-file-write-promotion`
  Purpose: Create isolated copy-on-write workspaces combining immutable source snapshots, writable conversion overlays, durable staged output, and disposable scratch data.
- `elmos-intermediate-artifact-manifest` — Intermediate Artifact Manifest  
  Dependencies: `elmos-content-addressable-storage`, `elmos-project-generation-file-staging`, `elmos-cache-metadata-database`
  Purpose: Standardize manifests for CST/AST, symbol tables, type/call/dataflow graphs, Semantic IR, mapping plans, generated fragments, patches, build outputs, tests, repair candidates, and certification evidence.

### P3-incremental

- `elmos-stage-contract-registry` — Stage Contract Registry  
  Dependencies: `elmos-cache-key-fingerprinting`, `elmos-intermediate-artifact-manifest`
  Purpose: Require every ELMOS stage to declare input/output schemas, determinism, fingerprint dimensions, cache policy, workspace mounts, resources, side effects, and checkpoint semantics.
- `elmos-semantic-interface-hashing` — Semantic and Public Interface Hashing  
  Dependencies: `elmos-project-snapshot-merkle`, `elmos-cache-key-fingerprinting`, `elmos-stage-contract-registry`
  Purpose: Separate raw implementation changes from public contract changes so unaffected dependents retain cache hits.
- `elmos-incremental-conversion-dag` — Incremental Conversion DAG  
  Dependencies: `elmos-project-snapshot-merkle`, `elmos-cache-key-fingerprinting`, `elmos-semantic-interface-hashing`, `elmos-stage-contract-registry`
  Purpose: Model conversion as a fine-grained deterministic DAG that re-executes only impacted parse, analysis, IR, planning, generation, build, test, repair, and certification nodes.

### P4-recovery

- `elmos-run-journal-state-machine` — Run Journal and State Machine  
  Dependencies: `elmos-cache-metadata-database`, `elmos-incremental-conversion-dag`, `elmos-project-generation-file-staging`
  Purpose: Persist authoritative run/node states, append-only events, leases, retries, pause, cancel, stale detection, and recovery ownership.
- `elmos-checkpoint-resume` — Checkpoint and Resume  
  Dependencies: `elmos-intermediate-artifact-manifest`, `elmos-run-journal-state-machine`, `elmos-content-addressable-storage`
  Purpose: Create durable checkpoints at stage and interval boundaries so service or worker failure resumes from verified state instead of restarting the full conversion.
- `elmos-generation-conflict-merge` — Generation Conflict and Merge  
  Dependencies: `elmos-project-generation-file-staging`, `elmos-atomic-file-write-promotion`, `elmos-intermediate-artifact-manifest`
  Purpose: Resolve collisions among generators, retries, framework adapters, previous generated output, and user edits without silent data loss.

### P5-distributed

- `elmos-remote-shared-cache` — Remote Shared Cache  
  Dependencies: `elmos-content-addressable-storage`, `elmos-action-cache`, `elmos-cache-metadata-database`, `elmos-cache-api-cli-contracts`
  Purpose: Scale reuse across workers and teams with S3/MinIO blobs, PostgreSQL metadata, optional Redis leases/hot indexes, resumable transfer, and trust namespaces.
- `elmos-native-build-cache-adapters` — Native Build Cache Adapters  
  Dependencies: `elmos-action-cache`, `elmos-cache-key-fingerprinting`, `elmos-sandbox-overlay-workspaces`
  Purpose: Integrate ecosystem-native incremental caches while keeping ELMOS ActionResults, manifests, and evidence authoritative.

### P6-assurance

- `elmos-cache-security-provenance` — Cache Security and Provenance  
  Dependencies: `elmos-content-addressable-storage`, `elmos-action-cache`, `elmos-project-generation-file-staging`, `elmos-intermediate-artifact-manifest`, `elmos-remote-shared-cache`
  Purpose: Protect cache and staged output against poisoning, path attacks, malicious artifacts, secret leakage, stale evidence, and cross-tenant access.
- `elmos-cache-retention-gc` — Cache Retention and Garbage Collection  
  Dependencies: `elmos-content-addressable-storage`, `elmos-cache-metadata-database`, `elmos-intermediate-artifact-manifest`
  Purpose: Control storage growth using pins, protected roots, mark-and-sweep GC, grace periods, cost-based eviction, quarantine retention, and deletion receipts.
- `elmos-cache-observability-performance` — Cache Observability and Performance  
  Dependencies: `elmos-action-cache`, `elmos-project-generation-file-staging`, `elmos-run-journal-state-machine`, `elmos-remote-shared-cache`, `elmos-incremental-conversion-dag`
  Purpose: Instrument cache lookup, staging, promotion, recovery, GC, and publication; then tune hit rate and restore economics without weakening correctness.
- `elmos-cache-chaos-certification` — Chaos Testing and Production Certification  
  Dependencies: `elmos-atomic-file-write-promotion`, `elmos-checkpoint-resume`, `elmos-cache-security-provenance`, `elmos-cache-observability-performance`
  Purpose: Prove crash safety, determinism, security, and operational readiness through replayable fault injection and signed production certification.

### P6-optimization

- `elmos-cache-trace-replay-simulator` — Cache Trace Capture and Replay Simulator  
  Dependencies: `elmos-cache-observability-performance`, `elmos-action-cache`, `elmos-incremental-conversion-dag`
  Purpose: Capture privacy-safe ELMOS cache workloads and replay them deterministically across modern policies so policy selection is evidence-driven rather than assumed.
- `elmos-sota-cache-policy-portfolio` — SOTA Cache Policy Portfolio  
  Dependencies: `elmos-cache-trace-replay-simulator`, `elmos-content-addressable-storage`, `elmos-action-cache`
  Purpose: Implement a deployable portfolio of SIEVE, S3-FIFO, W-TinyLFU, size-aware and cost-aware policies with modern adaptive candidates and safe fallbacks.
- `elmos-dag-aware-cache-prefetch` — DAG-Aware Future-Reuse Prefetch and Placement  
  Dependencies: `elmos-sota-cache-policy-portfolio`, `elmos-incremental-conversion-dag`, `elmos-remote-shared-cache`, `elmos-project-generation-file-staging`
  Purpose: Exploit the known ELMOS conversion DAG to predict next use, protect imminent artifacts, prefetch selectively, and place work near cached state.
- `elmos-cost-aware-cache-admission` — Cost-Aware Admission, Retention, and Eviction  
  Dependencies: `elmos-sota-cache-policy-portfolio`, `elmos-cache-retention-gc`, `elmos-cache-observability-performance`
  Purpose: Optimize cache value using recomputation cost, token cost, artifact size, restore latency, validation value, reuse probability, and critical-path impact.
- `elmos-adaptive-cache-policy-orchestrator` — Adaptive Cache Policy Orchestrator  
  Dependencies: `elmos-sota-cache-policy-portfolio`, `elmos-cost-aware-cache-admission`, `elmos-cache-trace-replay-simulator`
  Purpose: Select and tune cache policies off the hot path using workload fingerprints, objective profiles, hysteresis, shadow evaluation, and safe rollback.
- `elmos-learning-augmented-cache-control` — Learning-Augmented Cache Control Plane  
  Dependencies: `elmos-adaptive-cache-policy-orchestrator`, `elmos-cache-security-provenance`, `elmos-cache-trace-replay-simulator`
  Purpose: Add S4-FIFO-style asynchronous parameter learning and optional low-overhead learned eviction experiments without putting ML on cache correctness paths.
- `elmos-cache-autotuning-certification` — Cache Autotuning and Production Certification  
  Dependencies: `elmos-learning-augmented-cache-control`, `elmos-dag-aware-cache-prefetch`, `elmos-cache-chaos-certification`
  Purpose: Benchmark, tune, canary, and certify adaptive cache policies against representative ELMOS traces with multi-objective and worst-cohort gates.

### P7-rollout

- `elmos-cache-rollout-end-to-end` — Rollout and End-to-End Integration  
  Dependencies: `elmos-cache-api-cli-contracts`, `elmos-incremental-conversion-dag`, `elmos-checkpoint-resume`, `elmos-generation-conflict-merge`, `elmos-native-build-cache-adapters`, `elmos-cache-retention-gc`, `elmos-cache-chaos-certification`, `elmos-cache-autotuning-certification`
  Purpose: Integrate deterministic caching, durable generated-file staging, adaptive SOTA policy optimization, DAG-aware prefetch, recovery, and certified rollout into the complete ELMOS conversion flow.

### P8-parity-foundation

- `elmos-provider-prompt-cache-adapters` — Provider Prompt Cache Adapters  
  Dependencies: `elmos-cache-api-cli-contracts`, `elmos-cache-security-provenance`, `elmos-cache-observability-performance`
  Purpose: Implement versioned OpenAI, Anthropic, and self-hosted prompt-prefix cache adapters with capability discovery, exact accounting, safe fallback, and provider-isolated namespaces.
- `elmos-canonical-prompt-prefix-layout` — Canonical Prompt Prefix Layout  
  Dependencies: `elmos-provider-prompt-cache-adapters`, `elmos-cache-key-fingerprinting`, `elmos-stage-contract-registry`
  Purpose: Build deterministic, cache-friendly prompt assembly that maximizes exact stable-prefix reuse while preserving policy, tool, schema, project, and task correctness.

### P9-context-runtime

- `elmos-append-only-repository-context-ledger` — Append-Only Repository Context Ledger  
  Dependencies: `elmos-canonical-prompt-prefix-layout`, `elmos-project-snapshot-merkle`, `elmos-semantic-interface-hashing`, `elmos-run-journal-state-machine`
  Purpose: Persist repository reads, summaries, diffs, stale markers, and tool observations as an append-only context ledger so unchanged conversation prefixes remain reusable across coding turns.
- `elmos-cache-preserving-context-compaction` — Cache-Preserving Context Compaction  
  Dependencies: `elmos-append-only-repository-context-ledger`, `elmos-intermediate-artifact-manifest`, `elmos-checkpoint-resume`
  Purpose: Compact long coding sessions without destroying stable prompt-prefix reuse, provenance, task state, or repository correctness.

### P10-environment-affinity

- `elmos-environment-snapshot-cache` — Environment Snapshot Cache  
  Dependencies: `elmos-sandbox-overlay-workspaces`, `elmos-native-build-cache-adapters`, `elmos-cache-security-provenance`, `elmos-cache-retention-gc`
  Purpose: Cache reproducible sandbox, toolchain, dependency, index, and setup state with precise invalidation so warm ELMOS tasks avoid repeated environment construction.
- `elmos-cache-affinity-routing` — Cache Affinity Routing  
  Dependencies: `elmos-provider-prompt-cache-adapters`, `elmos-environment-snapshot-cache`, `elmos-dag-aware-cache-prefetch`, `elmos-remote-shared-cache`
  Purpose: Route sessions and DAG nodes to provider cache shards, model replicas, workers, environment snapshots, and local CAS holdings that maximize verified reusable work without sacrificing fairness or availability.

### P11-parity-control-plane

- `elmos-multi-layer-cache-coordinator` — Multi-Layer Cache Coordinator  
  Dependencies: `elmos-cache-affinity-routing`, `elmos-cache-preserving-context-compaction`, `elmos-action-cache`, `elmos-checkpoint-resume`, `elmos-cost-aware-cache-admission`
  Purpose: Coordinate provider prompt caches, exact Action Cache, CAS, repository context, environment snapshots, native build caches, and staged artifacts as one correctness-preserving lookup and execution plan.
- `elmos-cache-miss-diagnostics` — Cache Miss Diagnostics and Invalidation Explainability  
  Dependencies: `elmos-multi-layer-cache-coordinator`, `elmos-cache-observability-performance`, `elmos-cache-key-fingerprinting`
  Purpose: Assign every cache miss, bypass, eviction, failed restore, and invalidation a precise machine-readable reason with causal lineage and remediation guidance.

### P12-parity-certification

- `elmos-codex-claude-parity-benchmark` — Codex/Claude-Class Cache Parity Benchmark  
  Dependencies: `elmos-cache-miss-diagnostics`, `elmos-cache-trace-replay-simulator`, `elmos-cache-chaos-certification`, `elmos-cache-autotuning-certification`
  Purpose: Benchmark ELMOS cache behavior using reproducible coding-agent workloads and hard gates for prompt-token reuse, exact work reuse, incremental invalidation, environment warm starts, recovery, latency, cost, and zero false hits.
- `elmos-cache-hit-slo-autotuning` — Cache Hit SLO Autotuning and Regression Control  
  Dependencies: `elmos-codex-claude-parity-benchmark`, `elmos-learning-augmented-cache-control`, `elmos-adaptive-cache-policy-orchestrator`
  Purpose: Continuously tune cache layout, admission, capacity, retention, routing, prefetch, compaction, and environment policy against parity SLOs with safe shadowing, canaries, drift detection, and automatic rollback.

### P13-parity-rollout

- `elmos-codex-claude-cache-parity-rollout` — Codex/Claude-Class Cache Parity End-to-End Rollout  
  Dependencies: `elmos-cache-rollout-end-to-end`, `elmos-cache-hit-slo-autotuning`, `elmos-multi-layer-cache-coordinator`, `elmos-codex-claude-parity-benchmark`
  Purpose: Integrate and release the complete ELMOS cache parity architecture across prompt, context, deterministic actions, artifacts, environments, routing, diagnostics, benchmarking, and continuous SLO control.

## Parity target summary

| Metric | Target |
|---|---:|
| Stable-turn cached-token reuse | >=90% |
| Unexpected full-prefix miss | <=2% |
| Exact rerun weighted Action reuse | >=99% |
| Small-edit weighted reuse | >=90% |
| Environment snapshot hit | >=95% |
| Restart sealed-artifact reuse | >=99.9% |
| Accepted false hits | 0 |

> These are certification gates. A production achievement claim requires a fresh measured report.
