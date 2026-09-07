# Content-Addressed Storage and Action Cache

- Skill: `elmos-content-addressed-cache`
- Priority: `P0`
- Phase: `G3`
- Dependencies: `elmos-architecture-contract-governance`, `elmos-repository-snapshot-workspace`

## Objective

Eliminate repeated parsing, generation, compilation, testing, model calls, and project copying without weakening correctness or tenant isolation.

## Task groups

### Digest and object model

- [ ] `ELMOS-CAS-001` Standardize SHA-256 digest with algorithm, lowercase hex, and size_bytes.
- [ ] `ELMOS-CAS-002` Define immutable Blob, Tree, Manifest, Action, and ActionResult schemas.
- [ ] `ELMOS-CAS-003` Canonicalize directory ordering, file modes, executable bits, symlinks, and metadata without changing file bytes.
- [ ] `ELMOS-CAS-004` Avoid implicit line-ending or encoding changes.
- [ ] `ELMOS-CAS-005` Attach tenant, project, source, schema, media type, sensitivity, and provenance metadata outside immutable content.

### CAS API and transfer

- [ ] `ELMOS-CAS-006` Implement existence checks and batch missing-digest queries.
- [ ] `ELMOS-CAS-007` Implement direct upload for small blobs and multipart upload for large blobs.
- [ ] `ELMOS-CAS-008` Support resumable chunks, per-chunk digest, compression, encryption, range reads, and bandwidth limits.
- [ ] `ELMOS-CAS-009` Recompute final digest before acceptance.
- [ ] `ELMOS-CAS-010` Quarantine mismatches and alert.
- [ ] `ELMOS-CAS-011` Support batch read/write and skip already-present blobs.
- [ ] `ELMOS-CAS-012` Avoid recompressing archives and compressed media.

### Storage tiers

- [ ] `ELMOS-CAS-013` Implement runner-local L1 CAS on high-performance disk.
- [ ] `ELMOS-CAS-014` Implement shared S3/MinIO-compatible L2 CAS.
- [ ] `ELMOS-CAS-015` Use read-through and controlled asynchronous write-back.
- [ ] `ELMOS-CAS-016` Require critical outputs to reach durable storage before completion.
- [ ] `ELMOS-CAS-017` Apply size-aware L1 eviction and expose reasons.
- [ ] `ELMOS-CAS-018` Support tenant encryption keys and regional policy.
- [ ] `ELMOS-CAS-019` Separate public dependency blobs from private source-derived objects.

### Action cache

- [ ] `ELMOS-CAS-020` Build canonical Action Key from source tree, dependency graph, adapter, IR schema, rule/mutation packs, toolchain image, target platform, build options, prompt, model, policy, permission scope, environment, and declared inputs.
- [ ] `ELMOS-CAS-021` Use immutable image digests rather than tags.
- [ ] `ELMOS-CAS-022` Normalize maps, arguments, environment, and outputs before hashing.
- [ ] `ELMOS-CAS-023` Store output manifest, exit code, redacted logs, duration, resource use, validation, provenance, and evidence in ActionResult.
- [ ] `ELMOS-CAS-024` Cache failures only under explicit short-lived policy; never cache transient environment failures as valid.
- [ ] `ELMOS-CAS-025` Record hit, miss, bypass, stale, denied, and invalidation reasons.

### Security and correctness

- [ ] `ELMOS-CAS-026` Require authenticated runner/service identity for writes.
- [ ] `ELMOS-CAS-027` Sign or attest high-risk results.
- [ ] `ELMOS-CAS-028` Verify tenant sharing, security tier, residency, permission scope, toolchain, policy, and provenance on reads.
- [ ] `ELMOS-CAS-029` Disable cross-tenant reuse of generated/source-derived outputs by default.
- [ ] `ELMOS-CAS-030` Sample-recompute hits to detect corruption or nondeterminism.
- [ ] `ELMOS-CAS-031` Quarantine failing cache nodes.
- [ ] `ELMOS-CAS-032` Test poisoning, confused deputy, permission downgrade, and cross-tenant reads.

### References and GC

- [ ] `ELMOS-CAS-033` Create references from snapshots, staging, workflows, evidence, releases, and legal holds.
- [ ] `ELMOS-CAS-034` Mark reachable object graphs before deletion.
- [ ] `ELMOS-CAS-035` Support dry run, minimum age, retention class, legal hold, and tenant deletion policy.
- [ ] `ELMOS-CAS-036` Generate deletion manifest and audit per batch.
- [ ] `ELMOS-CAS-037` Reconcile database references with object inventory.
- [ ] `ELMOS-CAS-038` Scan orphaned uploads, incomplete multipart sessions, missing blobs, and dangling manifests.

### Metrics

- [ ] `ELMOS-CAS-039` Measure source, parse, semantic, IR, dependency, toolchain, build, test, model-prefix, response, and final action cache outcomes.
- [ ] `ELMOS-CAS-040` Measure bytes, compute, model tokens, and wall-clock time avoided.
- [ ] `ELMOS-CAS-041` Benchmark a goal of at least 95 percent exact rerun Action Cache hit for unchanged inputs.
- [ ] `ELMOS-CAS-042` Explain unexpected misses and over-invalidation.

## Validation

- [ ] Upload, download, resume, corrupt, truncate, duplicate, and concurrently write blobs.
- [ ] Change each key input and confirm Action Key changes.
- [ ] Reduce permissions/change tenant/security tier and reject stale hits.
- [ ] Sample-recompute and compare output digests.
- [ ] Run GC with live, expired, legal-hold, orphaned, and incomplete objects.

## Exit gate

- [ ] Exact unchanged reruns reuse valid results.
- [ ] Changed toolchain, rule, model, prompt, policy, permission, or environment cannot hit old output.
- [ ] Large transfer resumes and detects corruption.
- [ ] Unauthorized tenants cannot discover/read private blobs.
- [ ] GC never removes reachable snapshots, staging, evidence, or releases.
