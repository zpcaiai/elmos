---
name: b34-large-artifact-regional-transfer
description: "Implement secure resumable large-artifact transfer with chunk manifests digests encryption compression deduplication region policy bandwidth budgets relays and cleanup across private runners and control planes."
---

## Operating mode

Work directly in the repository. Inspect existing Batch 20-33 contracts, repository inventories, graph/index services, workflow histories, runner fleets, caches, artifact stores, SCM integrations, CI/CD, budgets, telemetry, incidents, and evidence before editing. Implement the smallest production-shaped portfolio or scale slice that satisfies this skill; do not stop at architecture notes when executable discovery, typed contracts, distributed processing, recovery, benchmarks, and evidence can be added.

Read these shared contracts first:

- `../../../docs/batch34/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch34/QUALITY_GATES.md`
- `../../../docs/batch34/REPOSITORY_LAYOUT.md`
- `../../../docs/batch34/PORTFOLIO_MODEL.md`
- `../../../docs/batch34/SHARDING_AND_IDEMPOTENCY.md`
- `../../../docs/batch34/SCHEDULING_FAIRNESS.md`
- `../../../docs/batch34/CACHE_AND_TRANSFER_POLICY.md`
- `../../../docs/batch34/BENCHMARK_SPEC.md`
- `../../../docs/batch34/DR_AND_REPLAY_POLICY.md`
- `../../../docs/batch34/SECURITY_AND_DATA_BOUNDARIES.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch34/scaffold_portfolio_pack.py ...`
- `python3 scripts/batch34/validate_portfolio_pack.py ...`
- `python3 scripts/batch34/validate_dependency_graph.py ...`
- `python3 scripts/batch34/validate_work_units.py ...`
- `python3 scripts/batch34/run_portfolio_gate.py ...`

## Global constraints

- Treat every portfolio pack as an exact tenant, SCM scope, region, inventory snapshot, toolchain, scheduler, and benchmark tuple. A materially different portfolio or execution policy requires a new version or pack.
- Discover repositories and runtime consumers from multiple evidence sources. Do not treat a single SCM listing or CMDB export as complete.
- Use typed Portfolio Inventory, Dependency Graph, Work Unit Plan, Scale Profile, Campaign Plan, and DR Replay contracts. Do not implement scale behavior as ad hoc scripts or unbounded shell fan-out.
- All distributed activities must be idempotent or compensated, checkpointed, bounded, tenant isolated, and replayable. Persist commit tokens for external effects.
- Use stable IDs and immutable baselines for repositories, graph nodes, work units, artifacts, campaigns, and benchmark datasets.
- Enforce hard placement, data-region, attestation, source-egress, and tenant constraints before cache affinity, cost, or speed preferences.
- Content-addressed reuse requires complete input manifests, digest/signature verification, provenance, and explicit tenant/trust policy. Never reuse ambiguous or untrusted artifacts.
- Keep development, negative, holdout, and representative portfolio corpora physically separate. Do not tune thresholds, partitioning, scheduling, or cache policy from holdout results.
- Fix systemic defects in discovery, graphing, partitioning, indexing, workflows, schedulers, recipes, or manifests rather than patching hundreds of repositories independently.
- No scale claim may silently exclude failed, inaccessible, unsupported, or over-budget repositories. Unknown scope remains visible in all metrics.
- Protect customer branch rules, source code, artifacts, budgets, and data boundaries. Never force merge, broaden permissions, or relax security to improve throughput.
- Run narrow tests first, then scale, failure, holdout, representative portfolio, and conservative Batch 34 gate checks before release claims.

## Skill 1254: Large artifact and cross-region resumable transfer

## Use this skill when

- Source snapshots, UIR, build outputs, test evidence, or release bundles exceed ordinary upload limits.
- Private runners and regions require interrupted transfer recovery.
- Bandwidth, egress cost, residency, and content policies must be enforced.

## Domain-specific risks and invariants

- Partial uploads can produce corrupt artifacts.
- Cross-region transfer can violate residency or create unexpected cost.
- Compression, deduplication, and encryption can interact with integrity and cache identity.

## Workflow

1. Define artifact classification, allowed source/destination regions, chunk size, manifest format, digest tree, encryption, compression, relay, bandwidth, and TTL.
2. Implement chunked upload/download, resumable sessions, deduplication, integrity verification, and atomic commit.
3. Bind transfer authorization to tenant, artifact, job, runner, destination, and expiry.
4. Apply DLP and source-egress policy before transfer.
5. Implement relay/proxy and offline bundle paths where direct transfer is prohibited.
6. Handle interruption, retry, duplicate chunks, expired sessions, corruption, and cleanup.
7. Measure throughput, egress, storage, resume efficiency, and cost on representative sizes.

## Required repository outputs

- Transfer policy and chunk manifest schema
- Regional route, encryption, bandwidth, and cleanup configuration
- Interruption/resume, corruption, authorization, residency, and cost evidence

## Verification

- Interrupt transfers at multiple percentages and verify exact final digest.
- Attempt unauthorized region, tenant, and artifact transfers.
- Verify abandoned sessions and chunks are cleaned according to policy.

## Stop and escalate when

- Residency or ownership does not permit the proposed route.
- Encryption keys or relay trust are not approved.
- Final artifact integrity cannot be proven.

## Definition of done

- Large transfers resume safely and commit atomically.
- Unauthorized or noncompliant routes are blocked.
- Cost and cleanup are evidenced.
