---
name: elmos-repository-snapshot-workspace
description: Pin inputs to immutable commits, create canonical snapshots, enforce
  source residency, and manage isolated leased workspaces.
version: 1.0.0
priority: P0
phase: G3
dependencies:
- elmos-identity-tenant-security
- elmos-temporal-task-reliability
---

# Immutable Repository Snapshot and Workspace Lease

## Objective

Make every migration or generation result reproducible against an immutable source while keeping customer source inside authorized execution boundaries.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Immutable Repository Snapshot and Workspace Lease** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-identity-tenant-security`
- `elmos-temporal-task-reliability`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- A branch is discovery input; every run pins a commit SHA.
- Force-push never mutates historical snapshots.
- Each task receives an isolated writable workspace and immutable source snapshot.
- Customer source is local-only by default.

## Required inputs

- Provider installation and repository identity.
- Requested ref and resolved commit.
- Submodule/LFS policies.
- Tenant source-residency and retention policy.

## Required outputs

- `Canonical snapshot manifest/digest.`
- `Workspace lease lifecycle.`
- `Source-local-only, encrypted-upload, and derived-artifact modes.`
- `Retention, cleanup, and audit evidence.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

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

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Resolve the same commit twice and compare digests.
- [ ] Force-push and confirm historical snapshot remains unchanged.
- [ ] Attempt cross-tenant workspace/snapshot access.
- [ ] Kill runner before upload and verify cleanup waits for reconciliation.
- [ ] Verify SOURCE_LOCAL_ONLY reports zero raw source bytes uploaded.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Every project references immutable commit and snapshot digest.
- [ ] Workspaces are isolated, leased, recoverable, and safely cleaned.
- [ ] Force-push cannot rewrite evidence.
- [ ] Residency policy is enforced and measurable.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
