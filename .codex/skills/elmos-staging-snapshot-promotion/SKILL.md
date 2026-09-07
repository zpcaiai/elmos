---
name: elmos-staging-snapshot-promotion
description: Implement copy-on-write staging, immutable sealed snapshots, validation
  boundaries, conflict-safe overlays, and idempotent promotion to artifacts, Git,
  and pull requests.
version: 1.0.0
priority: P0
phase: G3
dependencies:
- elmos-content-addressed-cache
- elmos-temporal-task-reliability
---

# Project Generation Staging, Sealing, Validation, and Promotion

## Objective

Allow project generation and conversion to pause, resume, validate, compare, rollback, and promote without copying or corrupting full projects.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Project Generation Staging, Sealing, Validation, and Promotion** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-content-addressed-cache`
- `elmos-temporal-task-reliability`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Source snapshots are never modified.
- SEALED and VALIDATED staging states are immutable.
- Validation writes only declared outputs/evidence.
- Promotion is idempotent and never destroys the last validated snapshot.

## Required inputs

- Source snapshot digest.
- Target profile, toolchain, rule pack, policy, and generation plan.
- CAS and workspace lease.
- Promotion destination and approval policy.

## Required outputs

- `Staging lifecycle and copy-on-write overlays.`
- `Sealed Merkle manifest.`
- `Validation boundary.`
- `Idempotent promotion and rollback.`
- `Retention/audit evidence.`

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

- [ ] Interrupt before seal, after seal, during validation, and during promotion, then resume correctly.
- [ ] Attempt writes after seal/validation.
- [ ] Run two agents changing the same file.
- [ ] Retry branch, commit, PR, and export and verify idempotency.
- [ ] Verify unchanged files reuse CAS blobs.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Generation resumes from latest valid sealed state.
- [ ] Failed validation cannot corrupt prior validated state.
- [ ] Every output file is traceable to source/rule/model/tool/human.
- [ ] Repeated promotion creates no duplicates.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
