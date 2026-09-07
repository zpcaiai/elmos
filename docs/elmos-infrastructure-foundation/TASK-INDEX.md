# Task Index

Total tasks: **719**

## `elmos-infrastructure-program-orchestrator`

### Discovery and baseline

- [ ] `ELMOS-ORCH-001` Inventory applications, workers, runners, engines, platform modules, contracts, schemas, migrations, CI, deployment files, and skills.
- [ ] `ELMOS-ORCH-002` Identify authoritative stores for project, workflow, task, artifact, audit, billing, policy, and evidence.
- [ ] `ELMOS-ORCH-003` Detect placeholders, in-memory production state, trusted headers, default secrets, unprotected endpoints, and unexecuted integrations.
- [ ] `ELMOS-ORCH-004` Run the repository test suite and capture exact command, commit, environment, result, duration, and failures.
- [ ] `ELMOS-ORCH-005` Create a gap map from code to the selected acceptance gate.

### Planning and dependency control

- [ ] `ELMOS-ORCH-006` Load the skill manifest and task catalog before selecting work.
- [ ] `ELMOS-ORCH-007` Resolve all dependencies and approved exceptions.
- [ ] `ELMOS-ORCH-008` Select the smallest vertical slice that produces a demonstrable end-to-end result.
- [ ] `ELMOS-ORCH-009` Split work into reversible commits, migrations, checkpoints, and rollback boundaries.
- [ ] `ELMOS-ORCH-010` Attach validation commands and expected evidence to every task.
- [ ] `ELMOS-ORCH-011` Estimate system wall-clock runtime from measured history and label uncertainty.
- [ ] `ELMOS-ORCH-012` Estimate human-equivalent effort separately.
- [ ] `ELMOS-ORCH-013` Reserve compute, model, storage, network, and review budgets.

### Execution and handoff

- [ ] `ELMOS-ORCH-014` Create or update the durable implementation-plan YAML before editing.
- [ ] `ELMOS-ORCH-015` Implement production code, schema, tests, telemetry, audit, documentation, and runbook changes together.
- [ ] `ELMOS-ORCH-016` Classify failures as environment, dependency, code, policy, security, data, capacity, provider, or unknown.
- [ ] `ELMOS-ORCH-017` Place irreconcilable results in BLOCKED or MANUAL_RECOVERY rather than hiding partial failure.
- [ ] `ELMOS-ORCH-018` Checkpoint after each successful validation boundary and store large outputs by digest.
- [ ] `ELMOS-ORCH-019` Update status, commit, commands, measured duration, cost, evidence digest, and residual risk.
- [ ] `ELMOS-ORCH-020` Report the next dependency-resolved task and why it is next.
- [ ] `ELMOS-ORCH-021` Emit CERTIFIED, LIMITED, EXPERIMENTAL, or BLOCKED release status.

## `elmos-architecture-contract-governance`

### Architecture inventory

- [ ] `ELMOS-ARCH-001` Inventory each module, entry point, dependency, persistent state, network endpoint, and deployment mode.
- [ ] `ELMOS-ARCH-002` Draw control, workflow, execution, artifact, model, policy, evidence, data, and observability planes.
- [ ] `ELMOS-ARCH-003` Assign one authoritative owner for every core state domain.
- [ ] `ELMOS-ARCH-004` Find process-local state that would be lost on restart and assign a durable store.
- [ ] `ELMOS-ARCH-005` Mark modules that remain inside the modular monolith and justified independent workers.

### Architecture decisions

- [ ] `ELMOS-ARCH-006` Write an ADR for Temporal versus a custom workflow engine.
- [ ] `ELMOS-ARCH-007` Write an ADR for content-addressed storage versus project copying.
- [ ] `ELMOS-ARCH-008` Write an ADR for private-runner source residency.
- [ ] `ELMOS-ARCH-009` Write an ADR for deterministic rules before LLM repair.
- [ ] `ELMOS-ARCH-010` Write an ADR for event-plane responsibilities and why it does not replace workflows.
- [ ] `ELMOS-ARCH-011` Define ADR states proposed, accepted, superseded, rejected, and deprecated.

### Identifiers and states

- [ ] `ELMOS-ARCH-012` Standardize tenant, user, repository, snapshot, project, workflow, task, attempt, runner, artifact, evidence, approval, and policy identifiers.
- [ ] `ELMOS-ARCH-013` Replace free-form status strings with versioned enums.
- [ ] `ELMOS-ARCH-014` Define allowed state transitions and terminal states.
- [ ] `ELMOS-ARCH-015` Define idempotency key, receipt, transition ID, fencing token, correlation ID, trace ID, and audit ID formats.
- [ ] `ELMOS-ARCH-016` Add database uniqueness and transition constraints.

### API and schema governance

- [ ] `ELMOS-ARCH-017` Version external APIs under /api/v1 and define deprecation policy.
- [ ] `ELMOS-ARCH-018` Define a uniform error envelope with code, message, retryable, correlation_id, and details.
- [ ] `ELMOS-ARCH-019` Define pagination, filtering, sorting, ETag, conditional update, and idempotency semantics.
- [ ] `ELMOS-ARCH-020` Add schema_version to every cross-module DTO and event.
- [ ] `ELMOS-ARCH-021` Generate clients from OpenAPI and bindings from Protobuf.
- [ ] `ELMOS-ARCH-022` Reject removed required fields, reused Protobuf numbers, and incompatible enum changes in CI.
- [ ] `ELMOS-ARCH-023` Adopt canonical repository directories and ownership rules.

## `elmos-identity-tenant-security`

### OIDC and sessions

- [ ] `ELMOS-SEC-001` Add an OIDC resource server and validate issuer, audience, expiration, signature algorithm, nonce where applicable, and token type.
- [ ] `ELMOS-SEC-002` Resolve user only from validated token or server-side session.
- [ ] `ELMOS-SEC-003` Resolve active tenant from validated membership, never arbitrary headers.
- [ ] `ELMOS-SEC-004` Support multi-tenant membership and authorized tenant selection.
- [ ] `ELMOS-SEC-005` Check account disablement, membership revocation, and token/session revocation.
- [ ] `ELMOS-SEC-006` Proxy browser calls through a secure session layer and remove fixed tenant injection.
- [ ] `ELMOS-SEC-007` Implement a secure CLI login flow with short-lived credentials.

### RBAC and resource authorization

- [ ] `ELMOS-SEC-008` Create tenant, user_account, membership, role, permission, role_permission, and resource_grant tables.
- [ ] `ELMOS-SEC-009` Define owner, tenant admin, project admin, migration engineer, reviewer, approver, runner operator, auditor, billing admin, and read-only roles.
- [ ] `ELMOS-SEC-010` Authorize repository view, sync, clone, transform, and delivery separately.
- [ ] `ELMOS-SEC-011` Authorize project create, start, pause, resume, cancel, approve, archive, and delete separately.
- [ ] `ELMOS-SEC-012` Authorize runner enrollment, drain, disable, certificate rotation, and logs separately.
- [ ] `ELMOS-SEC-013` Authorize artifact read, export, retention override, and delete separately.
- [ ] `ELMOS-SEC-014` Authorize evidence, certification, policy exception, and approval separately.
- [ ] `ELMOS-SEC-015` Perform authorization in the service layer, not only UI.
- [ ] `ELMOS-SEC-016` Add IDOR and cross-resource tests.

### PostgreSQL RLS

- [ ] `ELMOS-SEC-017` Add tenant_id to every tenant-owned table and backfill safely.
- [ ] `ELMOS-SEC-018` Enable and force RLS on every tenant-owned table.
- [ ] `ELMOS-SEC-019` Create a migration role used only by schema tooling.
- [ ] `ELMOS-SEC-020` Create a non-owner, non-superuser runtime role without BYPASSRLS.
- [ ] `ELMOS-SEC-021` Set validated tenant context at transaction start and clear it before returning pooled connections.
- [ ] `ELMOS-SEC-022` Test that tenant variables cannot leak across pooled requests.
- [ ] `ELMOS-SEC-023` Fail startup if runtime user is owner, superuser, or BYPASSRLS.
- [ ] `ELMOS-SEC-024` Run cross-tenant attacks through application SQL and direct runtime-role SQL.

### Runner and service identity

- [ ] `ELMOS-SEC-025` Make enrollment tokens single-use, short-lived, scope-limited, and auditable.
- [ ] `ELMOS-SEC-026` Issue a unique runner identity after enrollment.
- [ ] `ELMOS-SEC-027` Authenticate runners with mTLS or equivalent workload identity.
- [ ] `ELMOS-SEC-028` Rotate runner certificates before expiry.
- [ ] `ELMOS-SEC-029` Support immediate revocation and deny-list propagation.
- [ ] `ELMOS-SEC-030` Authenticate internal services with mTLS and distinct audiences.
- [ ] `ELMOS-SEC-031` Ensure runner credentials cannot call user APIs.
- [ ] `ELMOS-SEC-032` Bind runner identity to tenant, region, capability, and permitted task scopes.

### Secret broker

- [ ] `ELMOS-SEC-033` Define SecretReference and remove plaintext credentials from task/workflow payloads.
- [ ] `ELMOS-SEC-034` Implement Vault, cloud secret manager, and development-only local adapters.
- [ ] `ELMOS-SEC-035` Lease GitHub, Maven, Gradle, npm, NuGet, PyPI, registry, database, and cloud credentials only at execution time.
- [ ] `ELMOS-SEC-036` Issue least-privilege credentials separately for clone, build, publish, and delivery.
- [ ] `ELMOS-SEC-037` Revoke secrets after completion, cancellation, timeout, or lease loss.
- [ ] `ELMOS-SEC-038` Redact secrets from logs, errors, traces, command lines, environment dumps, artifacts, and Evidence Packs.
- [ ] `ELMOS-SEC-039` Audit secret-reference access without values.
- [ ] `ELMOS-SEC-040` Fail non-development startup on empty/default/placeholder secrets.

### API and webhook hardening

- [ ] `ELMOS-SEC-041` Set request-body limits for JSON, upload, webhook, and log endpoints.
- [ ] `ELMOS-SEC-042` Apply user, tenant, IP, route, and expensive-operation rate limits.
- [ ] `ELMOS-SEC-043` Set request, upstream, idle, and streaming timeouts.
- [ ] `ELMOS-SEC-044` Configure CORS, Origin, CSRF, security headers, and cookie policy.
- [ ] `ELMOS-SEC-045` Move management endpoints to an internal port/network.
- [ ] `ELMOS-SEC-046` Validate webhook signature, delivery ID, timestamp, type, and replay window.
- [ ] `ELMOS-SEC-047` Encrypt or minimize raw webhook envelopes and apply retention.
- [ ] `ELMOS-SEC-048` Add privacy-safe structured request logs and correlation IDs.

## `elmos-temporal-task-reliability`

### State machines

- [ ] `ELMOS-WF-001` Define truthful project states including CANCEL_REQUESTED, CANCELLING, RECONCILING, UNKNOWN_RESULT, and MANUAL_RECOVERY.
- [ ] `ELMOS-WF-002` Define task states including lease, run, cancel, completing, expired, unknown, and quarantine.
- [ ] `ELMOS-WF-003` Create an allowed-transition table and reject illegal transitions.
- [ ] `ELMOS-WF-004` Generate unique transition IDs and enforce uniqueness.
- [ ] `ELMOS-WF-005` Write transition, outbox, and audit atomically.
- [ ] `ELMOS-WF-006` Prevent approval before a plan exists.

### Idempotent start

- [ ] `ELMOS-WF-007` Generate deterministic Workflow ID at project creation.
- [ ] `ELMOS-WF-008` Support Idempotency-Key on start and side-effecting commands.
- [ ] `ELMOS-WF-009` Use compare-and-set, transactional outbox, or Temporal Update-with-Start to remove dual-write race.
- [ ] `ELMOS-WF-010` Return existing workflow for duplicate start.
- [ ] `ELMOS-WF-011` Test concurrent starts and failures between each write.

### Activity correctness

- [ ] `ELMOS-WF-012` Replace generic workflow runtime exceptions with explicit application failures or modeled states.
- [ ] `ELMOS-WF-013` Wrap workflows so FAILED or CANCELLED is always persisted.
- [ ] `ELMOS-WF-014` Set per-activity timeouts, heartbeat, and retry policies.
- [ ] `ELMOS-WF-015` Heartbeat parse, build, transform, verification, transfer, and model work.
- [ ] `ELMOS-WF-016` Store checkpoint references in heartbeat details.
- [ ] `ELMOS-WF-017` Use versioned records and stable data conversion.
- [ ] `ELMOS-WF-018` Add Workflow Versioning, Search Attributes, and Continue-As-New.

### Lease and fencing

- [ ] `ELMOS-WF-019` Add attempt, lease_generation, lease_expires_at, fencing_token, receipt_id, and checkpoint to tasks.
- [ ] `ELMOS-WF-020` Implement acknowledgement and periodic renewal.
- [ ] `ELMOS-WF-021` Require attempt/generation on heartbeat, complete, and fail.
- [ ] `ELMOS-WF-022` Reject late results from old or expired leases.
- [ ] `ELMOS-WF-023` Make repeated completion with the same receipt idempotent.
- [ ] `ELMOS-WF-024` Enter reconciliation on conflicting receipts.
- [ ] `ELMOS-WF-025` Reap expired work to UNKNOWN_RESULT.
- [ ] `ELMOS-WF-026` Reconcile workspace, process, artifact, PR, check, and billing before retry.
- [ ] `ELMOS-WF-027` Move irreconcilable work to MANUAL_RECOVERY.

### Cancel, pause, resume

- [ ] `ELMOS-WF-028` Add authorized project/task cancel APIs.
- [ ] `ELMOS-WF-029` Propagate cancel to workflow, activity, runner, and child processes.
- [ ] `ELMOS-WF-030` Persist CANCEL_REQUESTED and CANCELLING truthfully.
- [ ] `ELMOS-WF-031` Save final checkpoint and partial artifact manifest.
- [ ] `ELMOS-WF-032` Expose noninterruptible boundaries.
- [ ] `ELMOS-WF-033` Implement pause/resume and approval signals.
- [ ] `ELMOS-WF-034` Replace database polling with signals or async completion.
- [ ] `ELMOS-WF-035` On resume compare snapshot, toolchain, policy, rule, and target digests.

### Logs and operations

- [ ] `ELMOS-WF-036` Implement chunked logs with monotonic sequence numbers.
- [ ] `ELMOS-WF-037` Support resumable SSE or WebSocket streaming.
- [ ] `ELMOS-WF-038` Store large logs in CAS and only redacted summaries/references in database.
- [ ] `ELMOS-WF-039` Store stage input, output, evidence, status, duration, and cost digests.
- [ ] `ELMOS-WF-040` Prevent customer absolute paths in remote APIs.
- [ ] `ELMOS-WF-041` Scan for stuck workflows and reconcile database, workflow, tasks, and checkpoints.
- [ ] `ELMOS-WF-042` Provide dead-letter/manual recovery view.
- [ ] `ELMOS-WF-043` Retain compatible workflow code for replay.
- [ ] `ELMOS-WF-044` Add deterministic resume from latest valid checkpoint.

## `elmos-repository-snapshot-workspace`

### Acquisition

- [ ] `ELMOS-SNAP-001` Verify repository ownership by the authenticated provider installation.
- [ ] `ELMOS-SNAP-002` Resolve branch, tag, or PR to immutable commit SHA.
- [ ] `ELMOS-SNAP-003` Clone with least-privilege short-lived credentials and bounded history, object, file, and byte policy.
- [ ] `ELMOS-SNAP-004` Resolve submodules to fixed commits and record inaccessible/disallowed entries.
- [ ] `ELMOS-SNAP-005` Resolve Git LFS pointers and record object digests/sizes.
- [ ] `ELMOS-SNAP-006` Detect symlink escape, path traversal, case collisions, reserved names, and unsupported filesystem constructs.
- [ ] `ELMOS-SNAP-007` Apply maximum repository, file-count, single-file, and total-byte limits.

### Manifest and sealing

- [ ] `ELMOS-SNAP-008` Create a versioned manifest containing provider, installation, repository, commit, tree digest, submodules, LFS, modes, sizes, and policy decisions.
- [ ] `ELMOS-SNAP-009` Canonicalize ordering without changing bytes or line endings.
- [ ] `ELMOS-SNAP-010` Generate SHA-256 for the manifest.
- [ ] `ELMOS-SNAP-011` Seal the snapshot read-only.
- [ ] `ELMOS-SNAP-012` Ensure force-push or repository deletion cannot alter historical identity.
- [ ] `ELMOS-SNAP-013` Store provenance/references centrally and content according to residency policy.

### Workspace leases

- [ ] `ELMOS-SNAP-014` Create a workspace lease for every task attempt.
- [ ] `ELMOS-SNAP-015` Bind tenant, project, workflow, task, attempt, runner, snapshot, sandbox, and expiry.
- [ ] `ELMOS-SNAP-016` Use random non-guessable paths and never expose absolute customer paths.
- [ ] `ELMOS-SNAP-017` Renew workspace with the task lease.
- [ ] `ELMOS-SNAP-018` Give every tenant/task an independent writable layer.
- [ ] `ELMOS-SNAP-019` Before cleanup confirm outputs/checkpoints are durable.
- [ ] `ELMOS-SNAP-020` Support debug retention, legal hold, manual recovery, and expiry.
- [ ] `ELMOS-SNAP-021` Sanitize reused disks or forbid reuse for stronger isolation.

### Residency and cleanup

- [ ] `ELMOS-SNAP-022` Implement SOURCE_LOCAL_ONLY with zero raw source upload.
- [ ] `ELMOS-SNAP-023` Implement ENCRYPTED_SNAPSHOT_UPLOAD with envelope encryption, approval, and audit.
- [ ] `ELMOS-SNAP-024` Implement DERIVED_ARTIFACT_ONLY for IR, summaries, diagnostics, and evidence.
- [ ] `ELMOS-SNAP-025` Measure raw source bytes leaving the runner.
- [ ] `ELMOS-SNAP-026` Require approval for source export with recipient, purpose, digest, and expiry.
- [ ] `ELMOS-SNAP-027` Apply tenant-specific retention.
- [ ] `ELMOS-SNAP-028` Reconcile workspace after runner loss before retry.
- [ ] `ELMOS-SNAP-029` Scan expired, orphaned, and policy-violating workspaces and produce deletion manifests.

## `elmos-content-addressed-cache`

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

## `elmos-staging-snapshot-promotion`

### Lifecycle

- [ ] `ELMOS-STAGE-001` Create states CREATED, WRITABLE, SEALED, VALIDATING, VALIDATED, PROMOTING, PROMOTED, FAILED, ARCHIVED, and EXPIRED.
- [ ] `ELMOS-STAGE-002` Link staging to source snapshot, workflow, task attempt, target, toolchain, rules, policy, and owner.
- [ ] `ELMOS-STAGE-003` Allow modifications only in WRITABLE.
- [ ] `ELMOS-STAGE-004` Generate full tree manifest and Merkle root on SEAL.
- [ ] `ELMOS-STAGE-005` Reject writes after seal/validation.
- [ ] `ELMOS-STAGE-006` Keep validation outputs separate from generated source.
- [ ] `ELMOS-STAGE-007` Audit every transition and approval.

### Copy-on-write and overlays

- [ ] `ELMOS-STAGE-008` Reference unchanged source blobs instead of copying them.
- [ ] `ELMOS-STAGE-009` Create new blobs only for added/modified files.
- [ ] `ELMOS-STAGE-010` Support separate deterministic-rule, model-agent, and human overlays.
- [ ] `ELMOS-STAGE-011` Record provenance for every patch/file.
- [ ] `ELMOS-STAGE-012` Digest every patch and overlay.
- [ ] `ELMOS-STAGE-013` Detect conflicting writes and require deterministic merge or review.
- [ ] `ELMOS-STAGE-014` Rollback to any sealed snapshot.
- [ ] `ELMOS-STAGE-015` Validate paths, counts, output size, executable bits, and forbidden files.

### Validation boundary

- [ ] `ELMOS-STAGE-016` Enter VALIDATING only with a fixed sealed manifest.
- [ ] `ELMOS-STAGE-017` Run compile, tests, security, behavior, and evidence assembly against the sealed digest.
- [ ] `ELMOS-STAGE-018` Fail if validation unexpectedly modifies source and preserve before/after evidence.
- [ ] `ELMOS-STAGE-019` Retain failed debug snapshots according to policy.
- [ ] `ELMOS-STAGE-020` Bind VALIDATED to exact validation/evidence digest.

### Promotion

- [ ] `ELMOS-STAGE-021` Export ZIP/TAR with manifest and checksums.
- [ ] `ELMOS-STAGE-022` Materialize to local output directory.
- [ ] `ELMOS-STAGE-023` Create deterministic Git branch and thematic commits.
- [ ] `ELMOS-STAGE-024` Create/update one idempotent pull request and status checks.
- [ ] `ELMOS-STAGE-025` Verify validated digest immediately before promotion.
- [ ] `ELMOS-STAGE-026` Require approval for source export or production destination.
- [ ] `ELMOS-STAGE-027` Preserve validated snapshot if promotion fails and reconcile effects.
- [ ] `ELMOS-STAGE-028` Audit destination, commit, PR, artifact, checks, and evidence.

### Retention

- [ ] `ELMOS-STAGE-029` Apply separate retention to writable, sealed, validated, promoted, and failed-debug snapshots.
- [ ] `ELMOS-STAGE-030` Use CAS reachability and legal holds.
- [ ] `ELMOS-STAGE-031` Expire abandoned writable workspaces only after workflow/task reconciliation.

## `elmos-reproducible-toolchain`

### Toolchain manifest

- [ ] `ELMOS-TOOL-001` Record ID, version, image digest, OS, architecture, runtime, compiler, build tools, libraries, adapter, policy, dependency-cache scope, locale, timezone, network, random seed, CPU, GPU, and determinism.
- [ ] `ELMOS-TOOL-002` Include full toolchain digest in every Action Key and Evidence Pack.
- [ ] `ELMOS-TOOL-003` Maintain compatibility matrix rather than one target.
- [ ] `ELMOS-TOOL-004` Version/deprecate without mutating history.
- [ ] `ELMOS-TOOL-005` Reject execution when runner lacks required capability.

### Layered images

- [ ] `ELMOS-TOOL-006` Layer base OS, language runtime, compiler/build tools, framework pack, eLMOS adapter, and project dependencies.
- [ ] `ELMOS-TOOL-007` Use BuildKit-equivalent cache mounts for Maven, Gradle, npm/pnpm/yarn, NuGet, pip/uv, Cargo, Go modules, and others.
- [ ] `ELMOS-TOOL-008` Run non-root and minimize packages/capabilities.
- [ ] `ELMOS-TOOL-009` Use .dockerignore and immutable base digests.
- [ ] `ELMOS-TOOL-010` Generate SBOM, vulnerability/license report, provenance, and signature.
- [ ] `ELMOS-TOOL-011` Prevent secrets, source, and private URLs in image layers.

### Language/platform matrix

- [ ] `ELMOS-TOOL-012` Provide governed Java 8, 11, 17, and 21 environments.
- [ ] `ELMOS-TOOL-013` Provide Kotlin, .NET/MSBuild, Python legacy/modern/GPU, Node/TypeScript, Go, Rust, C/C++/LLVM, PHP, Dart/Flutter, Windows, macOS/Swift, and notebook environments as supported paths require.
- [ ] `ELMOS-TOOL-014` Record supported project ranges and incompatibilities.
- [ ] `ELMOS-TOOL-015` For GPU record model, compute capability, driver, runtime libraries, device count, precision, and determinism.
- [ ] `ELMOS-TOOL-016` Keep unsupported legacy runtimes isolated and offline by default.

### Dependency reproduction

- [ ] `ELMOS-TOOL-017` Verify Maven/Gradle wrappers and checksums.
- [ ] `ELMOS-TOOL-018` Verify npm/pnpm/yarn, Cargo, Python, NuGet, Go, Dart, and other lock files.
- [ ] `ELMOS-TOOL-019` Without lock files capture repository, version, checksum, license, and resolution graph.
- [ ] `ELMOS-TOOL-020` Broker private credentials per task.
- [ ] `ELMOS-TOOL-021` Isolate tenant-private caches and separate verified public cache.
- [ ] `ELMOS-TOOL-022` Support offline dependency bundles.
- [ ] `ELMOS-TOOL-023` Detect dependency confusion, unpinned/mutable artifacts, and repository fallback.

### Reproducibility and classification

- [ ] `ELMOS-TOOL-024` Run the same snapshot/toolchain on two clean runners and compare declared outputs.
- [ ] `ELMOS-TOOL-025` Normalize or document timestamps, archive ordering, random IDs, paths, and nondeterminism.
- [ ] `ELMOS-TOOL-026` Classify failures as environment, source, private repository, network, policy, capacity, or unknown.
- [ ] `ELMOS-TOOL-027` Detect build scripts modifying source.
- [ ] `ELMOS-TOOL-028` Emit reproducibility report and mark nonreproducible output LIMITED/BLOCKED.

### Warm pools

- [ ] `ELMOS-TOOL-029` Maintain toolchain-specific warm pools based on demand.
- [ ] `ELMOS-TOOL-030` Scale from queue age, cache locality, startup cost, and forecast.
- [ ] `ELMOS-TOOL-031` Drain/rotate safely on image, policy, or certificate changes.
- [ ] `ELMOS-TOOL-032` Measure cold start, warm start, dependency resolution, and cache hit.

## `elmos-incremental-semantic-index`

### Merkle changes

- [ ] `ELMOS-INC-001` Generate Merkle tree for every source snapshot.
- [ ] `ELMOS-INC-002` Detect add, modify, delete, move, permission, and type changes.
- [ ] `ELMOS-INC-003` Reuse identical blobs after moves.
- [ ] `ELMOS-INC-004` Version/digest eLMOS ignore rules independently of .gitignore.
- [ ] `ELMOS-INC-005` Produce changed-file and changed-module manifests.

### Incremental syntax

- [ ] `ELMOS-INC-006` Use Tree-sitter or equivalent incremental CST for supported languages.
- [ ] `ELMOS-INC-007` Include grammar version/options in parse cache key.
- [ ] `ELMOS-INC-008` Persist parse trees by digest and reparse only changed files.
- [ ] `ELMOS-INC-009` Preserve byte/line/column mapping and syntax-error nodes.
- [ ] `ELMOS-INC-010` Diagnose encoding, generated code, and parser recovery ambiguity.

### Semantic queries

- [ ] `ELMOS-INC-011` Define query keys and exact input dependencies.
- [ ] `ELMOS-INC-012` Reuse results when dependencies are unchanged.
- [ ] `ELMOS-INC-013` Invalidate only transitive dependents.
- [ ] `ELMOS-INC-014` Detect cycles, query explosions, nondeterministic ordering, and invalid cache.
- [ ] `ELMOS-INC-015` Parallelize independent modules and record hit/miss/recompute reason.

### Symbol and domain graph

- [ ] `ELMOS-INC-016` Define stable language-qualified symbol IDs including module, namespace, signature, and generic arity.
- [ ] `ELMOS-INC-017` Index definitions, references, calls, inheritance, implementation, reads, writes, publishes, subscribes, database queries, API exposure, configuration use, and module dependencies.
- [ ] `ELMOS-INC-018` Map routes to handlers/contracts.
- [ ] `ELMOS-INC-019` Map code to tables/columns, messages, configuration, services, and files.
- [ ] `ELMOS-INC-020` Store versioned graphs in PostgreSQL initially and expose a measured upgrade boundary.

### Impact analysis

- [ ] `ELMOS-INC-021` Compute direct/transitive symbol impact.
- [ ] `ELMOS-INC-022` Propagate across API, database, message, serialization, security, transaction, and configuration.
- [ ] `ELMOS-INC-023` Map impacted symbols to target generation and validation actions.
- [ ] `ELMOS-INC-024` Explain inclusion with graph paths.
- [ ] `ELMOS-INC-025` Escalate reflection, dynamic import, code generation, native calls, and framework magic conservatively.

### Test selection

- [ ] `ELMOS-INC-026` Build test-to-code maps from static references, coverage, framework metadata, and runtime traces.
- [ ] `ELMOS-INC-027` Select affected unit/integration tests and record why.
- [ ] `ELMOS-INC-028` Escalate public contract, persistence, security, concurrency, build-tool, or unknown changes to broader suites.
- [ ] `ELMOS-INC-029` Regularly compare incremental selection with full-suite results and fail on missed regressions.

### Metrics

- [ ] `ELMOS-INC-030` Measure parse, query, IR, build, and test cache hit.
- [ ] `ELMOS-INC-031` Measure unaffected work rerun after one-file changes.
- [ ] `ELMOS-INC-032` Benchmark a goal of no more than ten percent unnecessary reprocessing for representative local changes.
- [ ] `ELMOS-INC-033` Record false-negative and false-positive impact selections.

## `elmos-runner-scheduler-execution`

### Action protocol

- [ ] `ELMOS-RUN-001` Define Action with action digest, input root, toolchain, command, environment, working directory, outputs, resources, sandbox, network, secrets, timeout, priority, tenant, and project.
- [ ] `ELMOS-RUN-002` Define ActionResult with status, receipt, output manifest, exit code, logs, duration, resources, cost, validation, and provenance.
- [ ] `ELMOS-RUN-003` Require declared outputs and do not upload arbitrary workspace contents.
- [ ] `ELMOS-RUN-004` Check Action Cache before execution and publish valid results after completion.
- [ ] `ELMOS-RUN-005` Negotiate protocol versions and reject incompatible runners.

### Capabilities and health

- [ ] `ELMOS-RUN-006` Register OS, architecture, CPU, memory, disk, GPU, sandbox tiers, region, residency, network, prewarmed toolchains, cache summary, concurrency, and load.
- [ ] `ELMOS-RUN-007` Refresh capability on image, hardware, policy, or connectivity changes.
- [ ] `ELMOS-RUN-008` Bind capabilities to authenticated runner identity.
- [ ] `ELMOS-RUN-009` Expose heartbeat, drain, maintenance, disabled, unhealthy, and quarantine states.
- [ ] `ELMOS-RUN-010` Prevent incompatible/revoked runners from leasing.

### Fair scheduling

- [ ] `ELMOS-RUN-011` Implement priority classes, weighted fairness, tenant/project/task quotas, priority aging, deadlines, and bounded preemption.
- [ ] `ELMOS-RUN-012` Prevent noisy neighbors across runners, models, storage, network, and queues.
- [ ] `ELMOS-RUN-013` Reserve resources before lease and release on terminal/expired states.
- [ ] `ELMOS-RUN-014` Expose queue age, estimated start, no-runner reason, quota, and capacity forecast.
- [ ] `ELMOS-RUN-015` Require approval for quota/budget override.

### Locality and placement

- [ ] `ELMOS-RUN-016` Prefer runners holding inputs, dependency caches, and toolchains.
- [ ] `ELMOS-RUN-017` Balance locality against queue delay, transfer, startup, security, and residency.
- [ ] `ELMOS-RUN-018` Record placement scores and explanation.
- [ ] `ELMOS-RUN-019` Support region/customer-network affinity.
- [ ] `ELMOS-RUN-020` Avoid raw-source movement when private runner can execute locally.

### Fleet modes

- [ ] `ELMOS-RUN-021` Support trusted native local, rootless container, Kubernetes Job, warm Deployment, external private, Windows, macOS/Swift, ARM, and GPU runners.
- [ ] `ELMOS-RUN-022` Implement safe drain, certificate rotation, image rollout, and maintenance.
- [ ] `ELMOS-RUN-023` Autoscale warm pools from queue age, demand, cold-start cost, and forecast.
- [ ] `ELMOS-RUN-024` Keep capability labels immutable for the leased task.

### Sharding and recovery

- [ ] `ELMOS-RUN-025` Partition large repositories by module, dependency graph, work unit, or tests.
- [ ] `ELMOS-RUN-026` Store shard inputs/outputs in CAS with explicit dependencies.
- [ ] `ELMOS-RUN-027` Retry only failed shards.
- [ ] `ELMOS-RUN-028` Quarantine repeatedly failing shards while independent work continues.
- [ ] `ELMOS-RUN-029` Aggregate shard results deterministically into project/portfolio evidence.

### Artifact transfer

- [ ] `ELMOS-RUN-030` Transfer large artifacts with chunk manifests, hashes, encryption, compression, deduplication, resume, region policy, and bandwidth budget.
- [ ] `ELMOS-RUN-031` Verify every chunk and final manifest.
- [ ] `ELMOS-RUN-032` Clean incomplete sessions after reconciliation/retention.
- [ ] `ELMOS-RUN-033` Measure bytes transferred, avoided, retried, and rejected.

## `elmos-secure-sandbox-runtime`

### Policy contract

- [ ] `ELMOS-SBX-001` Define tiers S0 trusted native, S1 rootless OCI, S2 gVisor, S3 Firecracker/Kata, and S4 Wasmtime/WASI plugin.
- [ ] `ELMOS-SBX-002` Define filesystem, network, process, device, resource, secret, output, timeout, and audit fields.
- [ ] `ELMOS-SBX-003` Map repository sensitivity, tenant policy, action type, and risk to a minimum tier.
- [ ] `ELMOS-SBX-004` Reject scheduling when no runner can satisfy the required tier.
- [ ] `ELMOS-SBX-005` Version policy decisions and include their digest in action identity.

### Rootless OCI baseline

- [ ] `ELMOS-SBX-006` Run with non-root user, rootless runtime, read-only root filesystem, isolated writable workspace, and minimal capabilities.
- [ ] `ELMOS-SBX-007` Apply seccomp plus AppArmor or SELinux where supported.
- [ ] `ELMOS-SBX-008` Set CPU, memory, disk, PID, file-count, output-size, and wall-clock limits.
- [ ] `ELMOS-SBX-009` Deny Docker socket, host paths, devices, privileged mode, and namespace sharing.
- [ ] `ELMOS-SBX-010` Terminate complete child-process trees on cancel, timeout, or runner loss.
- [ ] `ELMOS-SBX-011` Detect path traversal, symlink escape, fork bomb, and workspace quota abuse.

### Network and egress

- [ ] `ELMOS-SBX-012` Default deny outbound and inbound network.
- [ ] `ELMOS-SBX-013` Route approved outbound traffic through an authenticated egress proxy.
- [ ] `ELMOS-SBX-014` Allowlist domain, resolved IP range, protocol, port, purpose, and expiry.
- [ ] `ELMOS-SBX-015` Deny cloud metadata, loopback escape, private networks, and unapproved DNS resolvers.
- [ ] `ELMOS-SBX-016` Restrict dependency downloads to approved registries/proxies and record destination/bytes.
- [ ] `ELMOS-SBX-017` Apply task and tenant bandwidth budgets with stop or approval behavior.

### Secret handling

- [ ] `ELMOS-SBX-018` Inject secrets through short-lived memory/file mechanisms rather than image layers or durable task records.
- [ ] `ELMOS-SBX-019` Issue least-privilege repository, registry, model, and signing credentials per operation.
- [ ] `ELMOS-SBX-020` Prevent secrets from entering command echo, logs, traces, checkpoints, caches, artifacts, or evidence.
- [ ] `ELMOS-SBX-021` Revoke credentials and erase temporary material on every terminal path.
- [ ] `ELMOS-SBX-022` Scan declared outputs and logs for secret patterns before upload.

### Strong isolation

- [ ] `ELMOS-SBX-023` Integrate gVisor for untrusted generated code and install scripts.
- [ ] `ELMOS-SBX-024` Provide Firecracker or Kata adapter for high-assurance multi-tenant/customer workloads.
- [ ] `ELMOS-SBX-025` Boot microVMs from signed immutable images and isolated kernels.
- [ ] `ELMOS-SBX-026` Use snapshot restore only from tenant-neutral prewarmed state.
- [ ] `ELMOS-SBX-027` Reissue identity and secrets after restore and erase disks/memory between tenants.
- [ ] `ELMOS-SBX-028` Capture runtime/kernel/image provenance in evidence.

### WASM plugins

- [ ] `ELMOS-SBX-029` Define a versioned Wasmtime Component/WASI ABI for rule and evidence plugins.
- [ ] `ELMOS-SBX-030` Grant explicit capabilities for files, clocks, randomness, environment, and network.
- [ ] `ELMOS-SBX-031` Set fuel, memory, output, and time limits.
- [ ] `ELMOS-SBX-032` Require signed plugin packages and compatible interface versions.
- [ ] `ELMOS-SBX-033` Contain plugin trap/crash without crashing the runner.

### Security operations

- [ ] `ELMOS-SBX-034` Record sandbox start, policy, denials, egress, resource termination, and cleanup events.
- [ ] `ELMOS-SBX-035` Quarantine a runner after integrity violations or repeated escape indicators.
- [ ] `ELMOS-SBX-036` Maintain escape, residual-data, metadata-access, secret-leak, and malicious-package regression suites.
- [ ] `ELMOS-SBX-037` Publish runbooks for cleanup failure, suspected compromise, and certificate revocation.

## `elmos-semantic-ir-compiler-platform`

### Layered IR contract

- [ ] `ELMOS-IR-001` Define Surface CST, Language Semantic IR, Canonical Semantic IR, Domain IR, Target Framework IR, and generated-source stages.
- [ ] `ELMOS-IR-002` Give every node a stable ID, schema version, source span, language/version, provenance, annotations, and extension envelope.
- [ ] `ELMOS-IR-003` Model modules, types, functions, properties, generics, exceptions, concurrency, resources, transactions, serialization, reflection, and side effects.
- [ ] `ELMOS-IR-004` Define Web, Data, AI/ML, Infrastructure, API, database, message, and configuration domain dialects.
- [ ] `ELMOS-IR-005` Define canonical ordering, deterministic serialization, digesting, and schema migration.
- [ ] `ELMOS-IR-006` Store large IR in CAS and metadata/index references in PostgreSQL.

### Adapter SPI

- [ ] `ELMOS-IR-007` Define frontend, backend, framework, type resolver, dependency resolver, runtime trace, build, and test-discovery interfaces.
- [ ] `ELMOS-IR-008` Require adapters to publish capability, supported versions, loss model, known gaps, required toolchain, and deterministic status.
- [ ] `ELMOS-IR-009` Negotiate schema/capability versions before execution.
- [ ] `ELMOS-IR-010` Include adapter binary/config digest in action keys and evidence.
- [ ] `ELMOS-IR-011` Provide conformance fixtures and compatibility tests for each adapter.

### Native language frontends

- [ ] `ELMOS-IR-012` Integrate javac/OpenRewrite for Java and Kotlin compiler APIs for Kotlin.
- [ ] `ELMOS-IR-013` Integrate Roslyn for C# and TypeScript Compiler API for TypeScript/JavaScript.
- [ ] `ELMOS-IR-014` Integrate LibCST plus AST and mypy/Pyright for Python.
- [ ] `ELMOS-IR-015` Integrate Clang LibTooling for C/C++/Objective-C.
- [ ] `ELMOS-IR-016` Integrate go/packages/go/types, rust-analyzer or rustc interfaces, SwiftSyntax/compiler APIs, PHP static analysis, and Dart Analyzer as applicable.
- [ ] `ELMOS-IR-017` Use Tree-sitter as incremental syntax/fallback layer, not the final authority for resolved semantics.

### Framework and domain modeling

- [ ] `ELMOS-IR-018` Implement Spring/Jakarta, ASP.NET, Django/Flask/ASGI, React/Vue, Flutter, persistence, messaging, authentication, caching, and deployment adapters.
- [ ] `ELMOS-IR-019` Map endpoints, middleware, filters, transactions, ORM mappings, configuration binding, scheduled jobs, and lifecycle hooks.
- [ ] `ELMOS-IR-020` Capture implicit framework behavior as explicit IR or an unresolved gap.
- [ ] `ELMOS-IR-021` Separate framework upgrade rules from cross-language translation rules.

### Rule and mutation runtime

- [ ] `ELMOS-IR-022` Define versioned Rule DSL, Mutation DSL, Scenario DSL, and Evidence DSL.
- [ ] `ELMOS-IR-023` Require preconditions, source/target ranges, risk, confidence, ordering, conflicts, reversibility, and idempotency declaration.
- [ ] `ELMOS-IR-024` Support dry run, match explanation, deterministic patch generation, dependency ordering, and composable campaigns.
- [ ] `ELMOS-IR-025` Run a second pass and require no new diff for idempotent recipes.
- [ ] `ELMOS-IR-026` Preserve original worktree and isolate each patch/change set.
- [ ] `ELMOS-IR-027` Emit rule-execution manifest with inputs, matches, outputs, skipped reasons, timing, and evidence.

### Source mapping and gaps

- [ ] `ELMOS-IR-028` Maintain generated node/file mappings back to source CST, semantic nodes, rules, and model edits.
- [ ] `ELMOS-IR-029` Represent unsupported, ambiguous, approximate, manual, and runtime-only semantics explicitly.
- [ ] `ELMOS-IR-030` Attach severity, affected symbols, remediation, evidence requirement, and certification impact.
- [ ] `ELMOS-IR-031` Expose gaps to planning, agent context, validation, review, and evidence pack.
- [ ] `ELMOS-IR-032` Prevent high-risk unresolved gaps from automatic promotion.

### IR quality gates

- [ ] `ELMOS-IR-033` Build CST-to-IR, IR-to-target, same-language round-trip, schema migration, source-map, overload, generics, inheritance, exception, transaction, concurrency, and reflection fixtures.
- [ ] `ELMOS-IR-034` Compare native compiler symbol resolution with canonical graph.
- [ ] `ELMOS-IR-035` Run deterministic-repeat tests across clean workers.
- [ ] `ELMOS-IR-036` Track IR coverage and unknown-node rates by language/framework/version.
- [ ] `ELMOS-IR-037` Reject adapters that silently ignore unknown node kinds.

## `elmos-model-gateway-agent-runtime`

### Catalog and provider abstraction

- [ ] `ELMOS-LLM-001` Define model provider, model revision, deployment, context, modality, tool, structured-output, residency, privacy, price, rate-limit, and lifecycle records.
- [ ] `ELMOS-LLM-002` Define normalized request, streaming event, response, usage, cost, finish reason, safety/refusal, and provider-error contracts.
- [ ] `ELMOS-LLM-003` Implement timeout, bounded retry, backoff, circuit breaker, concurrency/rate limits, and capability negotiation.
- [ ] `ELMOS-LLM-004` Preserve historical model identity/provenance after retirement.
- [ ] `ELMOS-LLM-005` Use secret references and short-lived provider credentials.

### Routing and policy

- [ ] `ELMOS-LLM-006` Classify tasks and prefer deterministic rule, local small model, medium code model, frontier model, then multi-model review.
- [ ] `ELMOS-LLM-007` Score candidates by capability, quality evidence, latency, cost, residency, confidentiality, health, and quota.
- [ ] `ELMOS-LLM-008` Enforce provider/model allowlists per tenant/repository/data class.
- [ ] `ELMOS-LLM-009` Provide primary/fallback routing without silently weakening policy.
- [ ] `ELMOS-LLM-010` Record route candidates, selected model, policy decision, degradation, and reason in trace/evidence.

### Hard budgets

- [ ] `ELMOS-LLM-011` Create tenant, portfolio, project, workflow, stage, agent-run, and call budgets.
- [ ] `ELMOS-LLM-012` Reserve estimated tokens/cost before each call and reconcile actual usage after completion.
- [ ] `ELMOS-LLM-013` Enforce maximum prompt/completion/total tokens, cost, calls, iterations, wall-clock, concurrency, and repair patches.
- [ ] `ELMOS-LLM-014` Stop repeated equivalent errors and non-improving loops.
- [ ] `ELMOS-LLM-015` Require time-limited approval for overrides and audit reserved/actual/forecast values.
- [ ] `ELMOS-LLM-016` Prevent races from overspending shared budgets.

### Prompt and skill registry

- [ ] `ELMOS-LLM-017` Store immutable versioned system prompts, task prompts, structured-output schemas, examples, and linked Skill/Rule packages.
- [ ] `ELMOS-LLM-018` Digest every prompt/context template and include it in action/provenance keys.
- [ ] `ELMOS-LLM-019` Require evaluation and review before promotion.
- [ ] `ELMOS-LLM-020` Support shadow, canary, rollback, deprecation, and tenant override within policy.
- [ ] `ELMOS-LLM-021` Block embedded secrets and uncontrolled dynamic instructions.

### Semantic context builder

- [ ] `ELMOS-LLM-022` Start from target symbols/gaps and select callers, callees, types, contracts, tests, configuration, database/message schemas, rules, and prior validated decisions.
- [ ] `ELMOS-LLM-023` Score and explain every selected context block.
- [ ] `ELMOS-LLM-024` Use exact snapshot/digest references and prevent stale-context mixing.
- [ ] `ELMOS-LLM-025` Apply token budgets through semantic compression/summarization without dropping binding contracts.
- [ ] `ELMOS-LLM-026` Keep tenant/project memory isolated and validate reusable knowledge before promotion.
- [ ] `ELMOS-LLM-027` Emit a context manifest suitable for replay and cache identity.

### Caching and local inference

- [ ] `ELMOS-LLM-028` Support local vLLM/SGLang or equivalent endpoints with health and capacity registration.
- [ ] `ELMOS-LLM-029` Arrange stable policy/skill/project context to maximize prefix cache safely.
- [ ] `ELMOS-LLM-030` Use exact response caching only when model revision, prompt, context, parameters, schema, policy, and permissions match.
- [ ] `ELMOS-LLM-031` Do not use fuzzy semantic cache for executable code transformations by default.
- [ ] `ELMOS-LLM-032` Partition or encrypt cache by tenant/data class and recheck authorization on lookup.
- [ ] `ELMOS-LLM-033` Measure prefix, exact, provider, and miss reason metrics.

### Tool-controlled agent loop

- [ ] `ELMOS-LLM-034` Bind each agent run to explicit file, shell, compiler, test, retrieval, network, and repository tool allowlists.
- [ ] `ELMOS-LLM-035` Validate tool parameters against schemas and policy before execution.
- [ ] `ELMOS-LLM-036` Run shell/build/test tools in the required sandbox and workspace.
- [ ] `ELMOS-LLM-037` Use idempotency keys/fencing for side-effecting tools.
- [ ] `ELMOS-LLM-038` Require approval for high-risk writes, dependency/security changes, export, or PR operations.
- [ ] `ELMOS-LLM-039` Record every tool request/result digest, decision, duration, and failure.
- [ ] `ELMOS-LLM-040` Prevent agents from changing their own policy, budget, identity, sandbox, or allowlist.

### Repair quality loop

- [ ] `ELMOS-LLM-041` Feed only classified failures and relevant semantic context to repair agents.
- [ ] `ELMOS-LLM-042` Create one isolated patch per iteration and run selected validation.
- [ ] `ELMOS-LLM-043` Track objective improvement, repeated signatures, regression count, and remaining gaps.
- [ ] `ELMOS-LLM-044` Escalate to full tests at risk thresholds and before promotion.
- [ ] `ELMOS-LLM-045` Stop and emit a human task when bounds or confidence fail.

## `elmos-verification-fabric`

### Baseline capture

- [ ] `ELMOS-VER-001` Reproduce source build in a sealed environment and classify environment, dependency, code, private-registry, infrastructure, and flaky failures.
- [ ] `ELMOS-VER-002` Record modules, build artifacts, discovered/executed/passed/failed/skipped tests, APIs, database/message schemas, side effects, performance, and resource profile.
- [ ] `ELMOS-VER-003` Freeze baseline snapshot/toolchain/scenario/tolerance digests.
- [ ] `ELMOS-VER-004` Separate pre-existing failures from migration regressions.
- [ ] `ELMOS-VER-005` Block unsupported claims when no trustworthy baseline can be captured.

### Compile and test normalization

- [ ] `ELMOS-VER-006` Run target compile, unit, integration, end-to-end, static analysis, lint, and package checks through language adapters.
- [ ] `ELMOS-VER-007` Normalize JUnit, pytest, dotnet, Go, Rust, JS, and other reports into versioned schemas.
- [ ] `ELMOS-VER-008` Track discovered test count and flag deletion/skip/selection changes.
- [ ] `ELMOS-VER-009` Classify failures before invoking agents.
- [ ] `ELMOS-VER-010` Use incremental test selection with conservative full-suite escalation.

### Contract verification

- [ ] `ELMOS-VER-011` Diff OpenAPI, GraphQL, Protobuf/gRPC, database schemas, events/messages, CLI, configuration, files, and public symbols.
- [ ] `ELMOS-VER-012` Classify compatible, potentially breaking, and breaking changes with affected consumers.
- [ ] `ELMOS-VER-013` Require approval and Known Deviation evidence for accepted breakage.
- [ ] `ELMOS-VER-014` Link every difference to source/target symbols and transformation provenance.

### Differential behavior

- [ ] `ELMOS-VER-015` Execute identical scenarios against baseline and target.
- [ ] `ELMOS-VER-016` Compare return values, errors, state/database changes, messages, files, logs/events, timing constraints, and external-effect intents.
- [ ] `ELMOS-VER-017` Normalize IDs, timestamps, ordering, randomness, locale, and nondeterministic fields only through explicit rules.
- [ ] `ELMOS-VER-018` Support exact, set/order-aware, absolute/relative numeric, temporal, and domain tolerances.
- [ ] `ELMOS-VER-019` Store minimized counterexamples and map them to symbols/IR/rules.

### Advanced validation

- [ ] `ELMOS-VER-020` Add golden snapshots, property-based tests, metamorphic tests, coverage-guided fuzzing, boundary/unicode/timezone/locale cases, serialization compatibility, transaction rollback, retry/idempotency, concurrency/race, and resource-leak tests.
- [ ] `ELMOS-VER-021` Use SMT/constraint checking for selected high-risk invariants.
- [ ] `ELMOS-VER-022` Model workflow/lease/recovery protocols with state-machine or formal specifications where valuable.
- [ ] `ELMOS-VER-023` Persist seeds and minimized cases for deterministic replay.

### Performance equivalence

- [ ] `ELMOS-VER-024` Define P50/P95/P99 latency, throughput, CPU, memory, disk, network, startup/cold-start, and cost thresholds.
- [ ] `ELMOS-VER-025` Run baseline and target with equivalent resources, warmup, dataset, load, and environment.
- [ ] `ELMOS-VER-026` Repeat runs, report uncertainty/noise, and distinguish statistical regression from fluctuation.
- [ ] `ELMOS-VER-027` Block promotion on unapproved regression and record approved tradeoffs.
- [ ] `ELMOS-VER-028` Link profiles and bottlenecks to commits/toolchains.

### Repair feedback

- [ ] `ELMOS-VER-029` Send only classified/minimized failures plus relevant context to an agent.
- [ ] `ELMOS-VER-030` Create isolated patch digest per iteration and rerun minimum valid checks.
- [ ] `ELMOS-VER-031` Escalate to full validation at risk thresholds and before certification.
- [ ] `ELMOS-VER-032` Reject repair attempts that delete tests, weaken assertions, disable security, or hide errors.
- [ ] `ELMOS-VER-033` Stop repeated/non-improving loops and create explicit human work.

### E1-E5 certification

- [ ] `ELMOS-VER-034` Define E1 buildable, E2 tests/contracts, E3 behavioral equivalence, E4 performance/security/resilience, and E5 shadow/canary/production migration evidence.
- [ ] `ELMOS-VER-035` Define mandatory evidence, tolerance, sample, approval, and expiry for each level.
- [ ] `ELMOS-VER-036` Emit CERTIFIED, LIMITED, EXPERIMENTAL, or BLOCKED with exact reasons.
- [ ] `ELMOS-VER-037` Never promote to a level with missing mandatory evidence.
- [ ] `ELMOS-VER-038` Support recertification after source, target, toolchain, rule, model, policy, or environment changes.

## `elmos-evidence-pack-offline-verification`

### Evidence data model

- [ ] `ELMOS-EVD-001` Define evidence pack/item, type, schema version, digest, size, producer, tenant, project, workflow, stage, task, attempt, timestamps, sensitivity, retention, and provenance.
- [ ] `ELMOS-EVD-002` Link items to source/target snapshots, action, toolchain, rule, prompt, model, policy, approvals, and certification.
- [ ] `ELMOS-EVD-003` Define mandatory/optional evidence by workflow and certification level.
- [ ] `ELMOS-EVD-004` Represent absent, failed, waived, superseded, and expired evidence explicitly.

### Evidence types

- [ ] `ELMOS-EVD-005` Capture source snapshot, inventory, dependency, toolchain, rule execution, model/agent, patch, build, tests, contracts, behavior, performance, security, supply chain, sandbox, resilience, cost, risk, approval, promotion, rollback, and DR evidence.
- [ ] `ELMOS-EVD-006` Use structured schemas plus referenced raw reports.
- [ ] `ELMOS-EVD-007` Normalize timestamps and canonicalize structured documents for digest/signature.

### Pack assembly

- [ ] `ELMOS-EVD-008` Build a deterministic directory/manifest containing every artifact path, media type, schema, digest, size, sensitivity, and relationship.
- [ ] `ELMOS-EVD-009` Include missing evidence, Known Deviations, Risk Register, Manual Tasks, certification, and verification instructions.
- [ ] `ELMOS-EVD-010` Reference large CAS objects or embed them according to export policy.
- [ ] `ELMOS-EVD-011` Generate ZIP/TAR plus overall digest without nondeterministic timestamps/order.
- [ ] `ELMOS-EVD-012` Scan the pack for secrets and prohibited source before release.

### Signing and trust

- [ ] `ELMOS-EVD-013` Sign canonical manifest and optionally individual high-value items.
- [ ] `ELMOS-EVD-014` Record signer identity, certificate/key reference, trust root, algorithm, time, and transparency/provenance where applicable.
- [ ] `ELMOS-EVD-015` Support enterprise/offline trust roots and rotation.
- [ ] `ELMOS-EVD-016` Reject altered, unknown, expired, or revoked signatures according to policy.

### Offline verifier

- [ ] `ELMOS-EVD-017` Provide elmos evidence verify with no control-plane dependency.
- [ ] `ELMOS-EVD-018` Verify archive safety, manifest schema, path uniqueness, size, digest, signature, trust, mandatory evidence, relationships, certification rules, and expiry.
- [ ] `ELMOS-EVD-019` Output human summary and stable JSON report with CERTIFIED/LIMITED/EXPERIMENTAL/BLOCKED plus reasons.
- [ ] `ELMOS-EVD-020` Support air-gapped operation and signed verifier releases/checksums.
- [ ] `ELMOS-EVD-021` Never execute project content during verification.

### Lifecycle and export

- [ ] `ELMOS-EVD-022` Apply tenant retention, legal hold, export, delete, redaction, and residency policies.
- [ ] `ELMOS-EVD-023` Keep immutable historical packs while allowing metadata supersession links.
- [ ] `ELMOS-EVD-024` Audit every export/download/delete/hold/sign/verify operation.
- [ ] `ELMOS-EVD-025` Reconcile pack references against CAS and backup state.

## `elmos-policy-supply-chain-signing`

### Policy engine and contract

- [ ] `ELMOS-POL-001` Integrate OPA/Rego or equivalent with versioned signed policy bundles.
- [ ] `ELMOS-POL-002` Define decision input/output with subject, tenant, resource, action, context, policy digest, allow/deny, rules, reasons, obligations, and expiry.
- [ ] `ELMOS-POL-003` Evaluate user/resource authorization, runner/action, sandbox, egress, secrets, model/provider, cache sharing, artifact export, license, vulnerability, budget override, approval, and production promotion.
- [ ] `ELMOS-POL-004` Cache only safe policy decisions with exact identity/context and short TTL.
- [ ] `ELMOS-POL-005` Fail closed for high-risk operations when policy is unavailable.

### Exception governance

- [ ] `ELMOS-POL-006` Require owner, scope, justification, compensating controls, approver, creation, expiry, and ticket for exceptions.
- [ ] `ELMOS-POL-007` Prevent permanent wildcard exceptions.
- [ ] `ELMOS-POL-008` Warn before expiry and automatically stop applying expired exceptions.
- [ ] `ELMOS-POL-009` Include exceptions in risk/evidence/certification decisions.
- [ ] `ELMOS-POL-010` Audit creation, use, renewal, and revocation.

### SBOM and dependency assurance

- [ ] `ELMOS-POL-011` Generate SBOM for toolchain images, adapters, skills/rules where applicable, and generated/converted projects.
- [ ] `ELMOS-POL-012` Scan vulnerabilities, licenses, secrets, containers, lockfiles, unpinned dependencies, typosquatting, dependency confusion, malicious packages, and provenance gaps.
- [ ] `ELMOS-POL-013` Distinguish source, build, test, runtime, optional, and transitive dependencies.
- [ ] `ELMOS-POL-014` Define severity/age/exploitability/usage-aware blocking policy.
- [ ] `ELMOS-POL-015` Rescan retained deliverables as intelligence changes and issue updated evidence without mutating old packs.

### Build provenance

- [ ] `ELMOS-POL-016` Generate provenance recording builder identity/version, source snapshot, action, toolchain, dependencies, parameters, policy, environment, outputs, and timestamps.
- [ ] `ELMOS-POL-017` Bind provenance to immutable digests and authenticated isolated builders.
- [ ] `ELMOS-POL-018` Prevent unsigned/untrusted builders from publishing production cache/results.
- [ ] `ELMOS-POL-019` Store provenance in CAS/evidence and make it independently verifiable.

### Signing and verification

- [ ] `ELMOS-POL-020` Sign OCI images, toolchains, Skill packages, Rule packs, plugins, generated artifacts, release archives, and Evidence Packs according to policy.
- [ ] `ELMOS-POL-021` Verify signatures/trust before runner execution, package installation, cache promotion, and release.
- [ ] `ELMOS-POL-022` Support keyless/managed and enterprise offline roots with rotation and revocation.
- [ ] `ELMOS-POL-023` Quarantine unsigned, invalid, revoked, or provenance-mismatched objects.
- [ ] `ELMOS-POL-024` Publish checksums and verification commands.

### Release gates

- [ ] `ELMOS-POL-025` Combine authorization, sandbox, tests, behavior, security, SBOM, license, provenance, signature, evidence, cost, and approval decisions.
- [ ] `ELMOS-POL-026` Return exact blocking reasons and remediation rather than a generic failure.
- [ ] `ELMOS-POL-027` Prevent an agent or project configuration from weakening organization policy.
- [ ] `ELMOS-POL-028` Record every gate input digest and decision for deterministic replay.

## `elmos-observability-finops`

### Telemetry conventions

- [ ] `ELMOS-OBS-001` Define spans/events for API, project, workflow, activity, lease, action, sandbox, transfer, cache, parser/IR/rule, model/tool, build/test, evidence, promotion, and recovery.
- [ ] `ELMOS-OBS-002` Propagate trace/correlation identifiers through HTTP, gRPC, Temporal, messages, runner protocol, model gateway, and artifact metadata.
- [ ] `ELMOS-OBS-003` Standardize tenant/project/workflow/task/action/runner/adapter/language/toolchain/rule/model/cache/sandbox/validation attributes.
- [ ] `ELMOS-OBS-004` Hash or omit sensitive tenant/source values and apply centralized redaction.
- [ ] `ELMOS-OBS-005` Separate management endpoints/network and protect telemetry export.

### Metrics and SLOs

- [ ] `ELMOS-OBS-006` Measure workflow starts/failures/stuck/duration/retries/heartbeat lag.
- [ ] `ELMOS-OBS-007` Measure queue age, lease expiry, unknown result, runner health/load, sandbox startup, transfer, and capacity.
- [ ] `ELMOS-OBS-008` Measure CAS/action/parse/IR/toolchain/prefix/response cache hits, misses, corruption, evictions, and bytes avoided.
- [ ] `ELMOS-OBS-009` Measure model requests/tokens/cost/latency/budget rejection/tool calls/iterations/repair success.
- [ ] `ELMOS-OBS-010` Measure compile/test/contract/behavior/performance/security/evidence/certification/PR quality outcomes.
- [ ] `ELMOS-OBS-011` Define availability, correctness, durability, recovery, latency, and freshness SLOs with burn-rate alerts.

### Logs, dashboards, and alerts

- [ ] `ELMOS-OBS-012` Emit structured logs with trace/correlation and schema versions.
- [ ] `ELMOS-OBS-013` Build system health, workflows, runner fleet, cache, model cost, quality/certification, tenant usage, storage, and DR dashboards.
- [ ] `ELMOS-OBS-014` Alert on queue age, lease/reaper anomalies, stuck workflow, CAS corruption, model budget spikes, evidence gaps, security denials, backup/restore failure, and SLO burn.
- [ ] `ELMOS-OBS-015` Attach owner, severity, runbook, deduplication, and escalation to each alert.
- [ ] `ELMOS-OBS-016` Test alerts through synthetic failure injection.

### Continuous profiling

- [ ] `ELMOS-OBS-017` Profile Java control plane/Temporal workers, Go runners, Python engines, native compilers, and inference services.
- [ ] `ELMOS-OBS-018` Correlate CPU, heap, allocation, lock, goroutine/thread, I/O, and flame profiles to actions/toolchains.
- [ ] `ELMOS-OBS-019` Detect repeated large-file reads, dependency downloads, serialization, low cache reuse, N+1 queries, queue contention, and high-token low-success paths.
- [ ] `ELMOS-OBS-020` Store profile summaries/evidence under retention policy without source leakage.

### Cost ledger and FinOps

- [ ] `ELMOS-OBS-021` Record compute CPU/memory/GPU time, runner startup/idle, storage, transfer, observability, provider tokens, licenses, and human review.
- [ ] `ELMOS-OBS-022` Aggregate by tenant, portfolio, project, workflow, stage, action, adapter, model, and certification.
- [ ] `ELMOS-OBS-023` Track estimate, reservation, actual, forecast, variance, refund, retry waste, cache savings, and cost per verified work unit.
- [ ] `ELMOS-OBS-024` Implement soft/hard budgets, anomaly detection, allocation tags, approval, and forecast.
- [ ] `ELMOS-OBS-025` Do not count transfers or retries twice.

### Autonomous runtime estimation

- [ ] `ELMOS-OBS-026` Predict eLMOS machine wall-clock duration from repository features, changed work units, cache state, queue/capacity, runner/toolchain locality, historical stage durations, model rate/latency, validation scope, retries, and uncertainty.
- [ ] `ELMOS-OBS-027` Return P50/P80/P95 duration ranges, confidence, assumptions, critical path, queue time, execution time, and risk drivers.
- [ ] `ELMOS-OBS-028` Continuously recalibrate estimates from actual stage completion and residual work.
- [ ] `ELMOS-OBS-029` Never express system ETA as developer person-days or include human waiting unless separately labeled.
- [ ] `ELMOS-OBS-030` Provide a separate human-equivalent estimate for manual implementation/review and clearly state it is a comparison, not the eLMOS runtime.
- [ ] `ELMOS-OBS-031` Persist estimate revisions and accuracy metrics in evidence.

### Operational data quality

- [ ] `ELMOS-OBS-032` Validate clock synchronization, duplicate events, missing spans, sampling bias, cost completeness, price version, and metric-label cardinality.
- [ ] `ELMOS-OBS-033` Reconcile model provider usage, runner records, object storage, and billing ledger.
- [ ] `ELMOS-OBS-034` Annotate dashboards/estimates when coverage is partial.

## `elmos-progressive-delivery`

### Feature flag foundation

- [ ] `ELMOS-REL-001` Provide provider-neutral OpenFeature-compatible evaluation.
- [ ] `ELMOS-REL-002` Target by tenant, repository, project, language path, adapter, risk, region, runner, and internal cohort.
- [ ] `ELMOS-REL-003` Record flag name/version/variant/reason/context digest in trace/evidence.
- [ ] `ELMOS-REL-004` Require authorization/audit for changes and approval for high-risk flags.
- [ ] `ELMOS-REL-005` Provide emergency kill switch independent of candidate service health.

### Shadow execution

- [ ] `ELMOS-REL-006` Run current and candidate engines/rules/prompts/models/toolchains from identical immutable inputs.
- [ ] `ELMOS-REL-007` Keep candidate outputs isolated and prevent external side effects.
- [ ] `ELMOS-REL-008` Compare patches, IR, compile/tests, contracts, behavior, performance, security, token/compute cost, runtime, and reviewer acceptance.
- [ ] `ELMOS-REL-009` Ensure candidate failure cannot fail the primary run.
- [ ] `ELMOS-REL-010` Store deterministic shadow evidence and sampling context.

### Canary controller

- [ ] `ELMOS-REL-011` Support staged cohorts such as internal, 1%, 5%, 20%, 50%, and 100%.
- [ ] `ELMOS-REL-012` Define minimum sample and thresholds for success, regression, unknown evidence, latency, cost, incidents, and certification.
- [ ] `ELMOS-REL-013` Pause automatically on insufficient data and rollback on severe regression.
- [ ] `ELMOS-REL-014` Prevent Simpson's-paradox-style aggregation by checking relevant repository/language/risk segments.
- [ ] `ELMOS-REL-015` Require explicit approval for final high-risk rollout.

### Compatibility releases

- [ ] `ELMOS-REL-016` Use expand/contract database migrations and compatibility windows.
- [ ] `ELMOS-REL-017` Preserve Protobuf field numbers and API versioning.
- [ ] `ELMOS-REL-018` Use Temporal workflow/activity versioning and retain replay-compatible code.
- [ ] `ELMOS-REL-019` Provide IR/schema migration and dual-read/write where required.
- [ ] `ELMOS-REL-020` Keep historical toolchain image, rule, prompt, model route, and policy digests available for rollback/replay.

### Rollback and learning

- [ ] `ELMOS-REL-021` Roll back routes/configuration first when safe, then workloads/toolchains/rules as required.
- [ ] `ELMOS-REL-022` Preserve generated artifacts/evidence for diagnosis without promoting them.
- [ ] `ELMOS-REL-023` Create regression cases from canary failures and require them before re-rollout.
- [ ] `ELMOS-REL-024` Audit rollout, pause, override, rollback, and kill-switch operations.

## `elmos-backup-recovery-replay`

### Recovery design

- [ ] `ELMOS-DR-001` Inventory authoritative state and derived/rebuildable indexes for PostgreSQL, Temporal, CAS/object storage, queues, configuration, policy, feature flags, trust roots, and secrets.
- [ ] `ELMOS-DR-002` Define RPO/RTO, recovery dependency order, owners, residency, encryption, retention, and point-of-no-return conditions.
- [ ] `ELMOS-DR-003` Document graceful degradation when a dependency is unavailable.
- [ ] `ELMOS-DR-004` Separate backup credentials/accounts/regions from runtime credentials.

### PostgreSQL recovery

- [ ] `ELMOS-DR-005` Configure encrypted full backups plus WAL/PITR.
- [ ] `ELMOS-DR-006` Test point-in-time, accidental delete, schema-upgrade, and region recovery.
- [ ] `ELMOS-DR-007` Restore with non-superuser runtime roles and verify RLS/security configuration.
- [ ] `ELMOS-DR-008` Reconcile outbox, audit, references, leases, budgets, and object manifests.
- [ ] `ELMOS-DR-009` Measure actual RPO/RTO and data loss window.

### CAS and object recovery

- [ ] `ELMOS-DR-010` Enable versioning/replication or offline backup according to data class.
- [ ] `ELMOS-DR-011` Preserve manifests and reference metadata needed to rebuild indexes.
- [ ] `ELMOS-DR-012` Run periodic digest/inventory sampling and orphan/missing-object reconciliation.
- [ ] `ELMOS-DR-013` Restore accidental deletes and region loss while respecting legal holds.
- [ ] `ELMOS-DR-014` Prevent lifecycle/GC from deleting unreconciled or protected recovery data.

### Temporal recovery and replay

- [ ] `ELMOS-DR-015` Back up persistence/visibility configuration and namespace/search-attribute settings.
- [ ] `ELMOS-DR-016` Retain replay-compatible workflow/activity code and data converters.
- [ ] `ELMOS-DR-017` Restore histories and run replay verification before resuming.
- [ ] `ELMOS-DR-018` Reconcile workflow projection, task leases, checkpoints, and side-effect receipts with PostgreSQL/CAS.
- [ ] `ELMOS-DR-019` Route non-replayable or ambiguous runs to MANUAL_RECOVERY with evidence.

### External side-effect reconciliation

- [ ] `ELMOS-DR-020` Reconcile repository branches/PRs/checks, webhooks, object uploads, notifications, signing, billing, and exports using idempotency receipts and provider state.
- [ ] `ELMOS-DR-021` Never retry UNKNOWN_RESULT before checking whether the side effect happened.
- [ ] `ELMOS-DR-022` Use fencing to reject stale attempts after recovery.
- [ ] `ELMOS-DR-023` Produce a decision record for retry, accept existing, compensate, forward-fix, or manual intervention.

### Recovery scopes

- [ ] `ELMOS-DR-024` Implement single task/project, runner/site, tenant, portfolio, service, storage, database, and regional recovery.
- [ ] `ELMOS-DR-025` Resume from last compatible sealed checkpoint rather than restarting completed stages.
- [ ] `ELMOS-DR-026` Allow partial portfolio recovery while quarantining ambiguous shards.
- [ ] `ELMOS-DR-027` Rebuild derived symbol/index/dashboard state from immutable sources.

### Exercises and evidence

- [ ] `ELMOS-DR-028` Schedule tabletop, component restore, partial outage, regional failover, corrupted object, expired key, non-replayable workflow, and full portfolio exercises.
- [ ] `ELMOS-DR-029` Use isolated test endpoints and synthetic fixtures.
- [ ] `ELMOS-DR-030` Generate DR evidence with inputs, actions, timings, loss, discrepancies, decisions, and remediation.
- [ ] `ELMOS-DR-031` Block production readiness when restore evidence is stale or unsuccessful.

## `elmos-scale-benchmark-certification`

### Fixture estate

- [ ] `ELMOS-BENCH-001` Create fixed small/medium/large/XL Java, Maven/Gradle multi-module, Spring legacy, database/message/cache, Python web/data/ML, .NET, TypeScript UI, native, and mixed-language monorepo fixtures.
- [ ] `ELMOS-BENCH-002` Include known semantic, dependency, build, flaky, security, performance, and recovery cases.
- [ ] `ELMOS-BENCH-003` Pin commits, dependencies, datasets, seeds, toolchains, and expected results.
- [ ] `ELMOS-BENCH-004` Exclude restricted customer source and license all fixtures.

### Cold, warm, and incremental runs

- [ ] `ELMOS-BENCH-005` Run empty-cache cold, full warm, single-file, single-symbol, module, dependency, toolchain, rule, prompt/model, policy, and permission-change scenarios.
- [ ] `ELMOS-BENCH-006` Measure every cache layer, invalidation reason, bytes transferred, stages recomputed, duration, cost, and quality.
- [ ] `ELMOS-BENCH-007` Sample-recompute warm hits and compare outputs to detect poisoning/staleness.
- [ ] `ELMOS-BENCH-008` Verify changed inputs invalidate exactly the required work.

### Scale profiles

- [ ] `ELMOS-BENCH-009` Define S under 50K LOC, M 50K-500K, L 500K-2M, XL above 2M, and portfolios of 100/1000 repositories with mixed languages.
- [ ] `ELMOS-BENCH-010` Measure inventory/index size, workflow history, queue, runner utilization, CAS, transfer, DB, model, validation, evidence, and cleanup.
- [ ] `ELMOS-BENCH-011` Exercise multi-repo dependencies, merge ordering, partial failure, quotas, fairness, and noisy neighbors.
- [ ] `ELMOS-BENCH-012` Report throughput, latency distributions, resource curves, bottlenecks, and saturation.

### Fault injection

- [ ] `ELMOS-BENCH-013` Restart control API/Temporal workers/runners, interrupt network, expire leases/certificates, degrade database/object storage/model providers, corrupt chunks/cache, duplicate webhooks/start/cancel/complete, exhaust quota/disk, and fail shards.
- [ ] `ELMOS-BENCH-014` Verify deterministic state, fencing, reconciliation, bounded retries, partial recovery, and no duplicate side effects.
- [ ] `ELMOS-BENCH-015` Generate reusable regression cases for every discovered failure.

### Security campaign

- [ ] `ELMOS-BENCH-016` Test cross-tenant database/CAS/cache/workspace/evidence access, stolen/revoked runner identity, sandbox escape/path traversal/metadata/egress, secret leakage, cache poisoning, malicious dependencies, prompt injection/tool escalation, unsigned artifacts, policy bypass, and export abuse.
- [ ] `ELMOS-BENCH-017` Use independent red-team assertions and preserve safe evidence.
- [ ] `ELMOS-BENCH-018` Block release on unresolved critical findings.

### Forecast and quality calibration

- [ ] `ELMOS-BENCH-019` Backtest machine wall-clock ETA P50/P80/P95, queue/capacity forecasts, cost forecasts, and automation confidence across cold/warm/change/scale/failure cohorts.
- [ ] `ELMOS-BENCH-020` Calibrate models continuously and report coverage/interval accuracy and segment bias.
- [ ] `ELMOS-BENCH-021` Keep human-equivalent effort comparison separate from autonomous runtime.
- [ ] `ELMOS-BENCH-022` Track compile, test retention, behavior, regression, repair, PR acceptance, evidence, source-egress, and cost-per-verified-workload.

### Pilot certification

- [ ] `ELMOS-BENCH-023` Select at least three structurally different real Java repositories with authorization and fixed commits.
- [ ] `ELMOS-BENCH-024` Complete source-local snapshot, baseline, health check, deterministic OpenRewrite path, compile/tests, classified long-tail repair, PR/checks, signed offline evidence, and repeat run.
- [ ] `ELMOS-BENCH-025` Record all failures, manual tasks, deviations, review time, source-egress bytes, runtime, and cost.
- [ ] `ELMOS-BENCH-026` Issue CERTIFIED/LIMITED/EXPERIMENTAL/BLOCKED based on exact gates.
- [ ] `ELMOS-BENCH-027` Do not claim commercial production readiness until the repeatable pilot and restore/security gates pass.

## `elmos-java-migration-production-loop`

### GitHub integration

- [ ] `ELMOS-JAVA-001` Sync installations/repositories and handle installation suspension/removal.
- [ ] `ELMOS-JAVA-002` Verify repository ownership by installation before access.
- [ ] `ELMOS-JAVA-003` Issue short-lived least-privilege clone and delivery tokens separately.
- [ ] `ELMOS-JAVA-004` Validate webhook signature/delivery id and handle rate limits, retry, GHES URL/API differences, and errors.
- [ ] `ELMOS-JAVA-005` Never store a long-lived PAT in project/task records.

### Snapshot and baseline

- [ ] `ELMOS-JAVA-006` Clone fixed commit with submodule/LFS/size/path policy into leased private workspace.
- [ ] `ELMOS-JAVA-007` Seal snapshot manifest/digest and enforce source-local or approved encrypted upload policy.
- [ ] `ELMOS-JAVA-008` Select signed JDK/build toolchain, validate wrappers, inject private registry secrets, and reproduce build.
- [ ] `ELMOS-JAVA-009` Record modules, dependencies, tests, artifacts, environment/code/private-registry failures, and source modifications.
- [ ] `ELMOS-JAVA-010` Capture pre-existing failures and baseline evidence.

### Health check and plan

- [ ] `ELMOS-JAVA-011` Build Maven/Gradle module graph and identify JDK, Spring, Security, Hibernate/JPA, Jakarta, testing, serialization, transaction, cache, messaging, API, database, and deployment fingerprints.
- [ ] `ELMOS-JAVA-012` Detect dependency conflicts, CVE/license candidates, unsupported plugins, reflection, native bindings, generated code, and compatibility risks.
- [ ] `ELMOS-JAVA-013` Select target profile and supported intermediate states such as Boot 2.7 to 3.x before later targets.
- [ ] `ELMOS-JAVA-014` Create dependency-aware migration DAG with deterministic probability, manual work, risk, evidence, budget, and system wall-clock ETA plus separate human-equivalent effort.
- [ ] `ELMOS-JAVA-015` Require plan review/approval before rewrite.

### Deterministic transformation

- [ ] `ELMOS-JAVA-016` Resolve a signed/versioned Recipe Catalog/BOM and license.
- [ ] `ELMOS-JAVA-017` Evaluate preconditions, dry run, affected modules/symbols, conflicts, and risk.
- [ ] `ELMOS-JAVA-018` Execute recipes in isolated staging and produce segmented thematic patches/commits.
- [ ] `ELMOS-JAVA-019` Run recipes twice and require no second diff where declared idempotent.
- [ ] `ELMOS-JAVA-020` Preserve original worktree and emit recipe execution manifest.

### Verification and long-tail repair

- [ ] `ELMOS-JAVA-021` Compile/test target and compare discovered/skipped/passed tests, APIs, contracts, dependencies, SBOM, security, and behavior against baseline.
- [ ] `ELMOS-JAVA-022` Classify failures before model use.
- [ ] `ELMOS-JAVA-023` Run repair agent only inside private sandbox with selected semantic context, tool/egress allowlist, hard budget, max iterations, and non-improvement stop.
- [ ] `ELMOS-JAVA-024` Reject test deletion, assertion weakening, security disabling, hidden exceptions, and unrelated broad changes.
- [ ] `ELMOS-JAVA-025` Escalate unresolved gaps to explicit human tasks.

### Delivery

- [ ] `ELMOS-JAVA-026` Seal validated target snapshot and build topic commits.
- [ ] `ELMOS-JAVA-027` Create/reconcile idempotent branch, PR, checks, labels, reviewers, and comments with minimal installation token.
- [ ] `ELMOS-JAVA-028` Include summary, migration plan, tests, risks, deviations, manual tasks, rollback, and evidence links.
- [ ] `ELMOS-JAVA-029` Generate and sign offline Evidence Pack and verification command.
- [ ] `ELMOS-JAVA-030` Keep customer as final merge authority and audit delivery operations.

### Repeatability and pilot

- [ ] `ELMOS-JAVA-031` Repeat the same fixed-commit migration and compare plan, deterministic patch, validation, and evidence digests.
- [ ] `ELMOS-JAVA-032` Test webhook duplication, concurrent start, runner loss, cancellation, provider error, PR response loss, and rollback.
- [ ] `ELMOS-JAVA-033` Run at least three authorized structurally different repositories before billable readiness.

## `elmos-production-readiness-gate`

### Implementation completeness

- [ ] `ELMOS-READY-001` Verify every required repository module, migration, API/schema, runner adapter, policy, dashboard, runbook, installer, and operational job exists in the target repository.
- [ ] `ELMOS-READY-002` Require code review, unit/integration/end-to-end tests, failure-path tests, and clean-environment reproduction.
- [ ] `ELMOS-READY-003` Distinguish generated task definitions from executed implementation.
- [ ] `ELMOS-READY-004` Reject placeholder, TODO-only, mock-only, or documentation-only completion for production gates.

### Security and tenancy gate

- [ ] `ELMOS-READY-005` Require trusted OIDC, membership-derived tenant, resource authorization, effective all-table RLS with non-superuser runtime role, unique rotating runner identity, short-lived secrets, sandbox/egress, audit, and cross-tenant attack tests.
- [ ] `ELMOS-READY-006` Require signed trusted toolchains/rules/skills/artifacts and passing supply-chain policy.
- [ ] `ELMOS-READY-007` Block unresolved critical/high security findings according to policy.

### Reliability and data gate

- [ ] `ELMOS-READY-008` Require idempotent workflow start/state transitions/side effects, lease renewal/reaper/fencing/reconciliation/cancel/checkpoint/replay, immutable snapshot/staging/CAS integrity, safe GC, and no duplicate PR/billing/export effects.
- [ ] `ELMOS-READY-009` Require backup restore and DR exercises within RPO/RTO.
- [ ] `ELMOS-READY-010` Require data retention/export/delete/legal-hold behavior.

### Transformation and quality gate

- [ ] `ELMOS-READY-011` Require reproducible toolchain/build, deterministic rules and second-run idempotency, semantic-gap reporting, preserved tests, compile/contract/behavior/performance/security validation, bounded agent repair, and certification evidence.
- [ ] `ELMOS-READY-012` Require no silent semantic loss or gate-gaming repairs.
- [ ] `ELMOS-READY-013` Define allowed Known Deviations and manual work.

### Operations and economics gate

- [ ] `ELMOS-READY-014` Require end-to-end trace/metrics/logs/redaction, tested alerts/runbooks, SLOs, capacity, cost ledger, budgets, source-egress metric, and calibrated machine wall-clock ETA.
- [ ] `ELMOS-READY-015` Require cost per verified work unit and forecast accuracy within declared tolerance.
- [ ] `ELMOS-READY-016` Keep human-equivalent effort comparison separate.

### Scale and pilot gate

- [ ] `ELMOS-READY-017` Require reproducible cold/warm/incremental/scale benchmarks, fault/security campaigns, restore/replay, and at least three repeatable authorized Java pilot repositories.
- [ ] `ELMOS-READY-018` Require reviewable PR/checks, signed offline evidence, explainable failure, customer merge control, and source-local default.
- [ ] `ELMOS-READY-019` Limit certification to actually tested languages, versions, deployment modes, scales, and security tiers.

### Decision and expiry

- [ ] `ELMOS-READY-020` Score each mandatory gate as PASS, FAIL, MISSING, STALE, WAIVED, or NOT_APPLICABLE with evidence digest.
- [ ] `ELMOS-READY-021` Emit CERTIFIED, LIMITED, EXPERIMENTAL, or BLOCKED and exact scope, conditions, expiry, owners, and remediation.
- [ ] `ELMOS-READY-022` Require independent approval for commercial release.
- [ ] `ELMOS-READY-023` Sign the readiness decision and include it in the release Evidence Pack.
- [ ] `ELMOS-READY-024` Automatically invalidate on critical source/toolchain/policy/schema/security/environment changes.
