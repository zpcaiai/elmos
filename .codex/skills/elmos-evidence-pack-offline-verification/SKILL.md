---
name: elmos-evidence-pack-offline-verification
description: Assemble signed, immutable, portable evidence that traces source, transformation,
  validation, risk, approval, cost, and delivery and can be verified without the control
  plane.
version: 1.0.0
priority: P0
phase: G7
dependencies:
- elmos-content-addressed-cache
- elmos-verification-fabric
- elmos-staging-snapshot-promotion
- elmos-policy-supply-chain-signing
---

# Immutable Evidence Pack, Offline Verification, and Delivery Provenance

## Objective

Turn each project generation or migration into an independently auditable delivery rather than an opaque output archive.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Immutable Evidence Pack, Offline Verification, and Delivery Provenance** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-content-addressed-cache`
- `elmos-verification-fabric`
- `elmos-staging-snapshot-promotion`
- `elmos-policy-supply-chain-signing`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Evidence references immutable digests and exact schema versions.
- Missing evidence is declared, never silently omitted.
- Secrets and unnecessary source content must not enter packs.
- Offline verification must not trust mutable service-side state.

## Required inputs

- Source/target/action/toolchain/rule/model manifests.
- Build, test, contract, behavior, performance, security, cost, risk, and approval results.
- Certification policy and tenant retention/export rules.

## Required outputs

- `Evidence schemas and immutable pack.`
- `Canonical manifest and signatures.`
- `Offline verifier CLI and machine-readable report.`
- `Retention, export, redaction, and integrity operations.`

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

- [ ] Alter one byte, remove an item, change manifest order/path, inject traversal/symlink, and verify failure.
- [ ] Verify with unknown/revoked/expired trust roots.
- [ ] Remove mandatory evidence and require downgraded/blocking status.
- [ ] Inject secret/source patterns and prevent export.
- [ ] Verify the same pack in an offline clean environment.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Every promoted delivery has a deterministic signed evidence pack.
- [ ] Tampering and missing evidence are detected offline.
- [ ] The pack explains source-to-output provenance, deviations, risk, approvals, and certification.
- [ ] Export contains no forbidden secret or source material.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
