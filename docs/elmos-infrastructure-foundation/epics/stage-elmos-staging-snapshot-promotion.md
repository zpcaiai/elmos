# Project Generation Staging, Sealing, Validation, and Promotion

- Skill: `elmos-staging-snapshot-promotion`
- Priority: `P0`
- Phase: `G3`
- Dependencies: `elmos-content-addressed-cache`, `elmos-temporal-task-reliability`

## Objective

Allow project generation and conversion to pause, resume, validate, compare, rollback, and promote without copying or corrupting full projects.

## Task groups

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

## Validation

- [ ] Interrupt before seal, after seal, during validation, and during promotion, then resume correctly.
- [ ] Attempt writes after seal/validation.
- [ ] Run two agents changing the same file.
- [ ] Retry branch, commit, PR, and export and verify idempotency.
- [ ] Verify unchanged files reuse CAS blobs.

## Exit gate

- [ ] Generation resumes from latest valid sealed state.
- [ ] Failed validation cannot corrupt prior validated state.
- [ ] Every output file is traceable to source/rule/model/tool/human.
- [ ] Repeated promotion creates no duplicates.
