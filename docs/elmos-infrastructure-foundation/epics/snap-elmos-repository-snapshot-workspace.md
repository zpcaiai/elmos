# Immutable Repository Snapshot and Workspace Lease

- Skill: `elmos-repository-snapshot-workspace`
- Priority: `P0`
- Phase: `G3`
- Dependencies: `elmos-identity-tenant-security`, `elmos-temporal-task-reliability`

## Objective

Make every migration or generation result reproducible against an immutable source while keeping customer source inside authorized execution boundaries.

## Task groups

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

## Validation

- [ ] Resolve the same commit twice and compare digests.
- [ ] Force-push and confirm historical snapshot remains unchanged.
- [ ] Attempt cross-tenant workspace/snapshot access.
- [ ] Kill runner before upload and verify cleanup waits for reconciliation.
- [ ] Verify SOURCE_LOCAL_ONLY reports zero raw source bytes uploaded.

## Exit gate

- [ ] Every project references immutable commit and snapshot digest.
- [ ] Workspaces are isolated, leased, recoverable, and safely cleaned.
- [ ] Force-push cannot rewrite evidence.
- [ ] Residency policy is enforced and measurable.
