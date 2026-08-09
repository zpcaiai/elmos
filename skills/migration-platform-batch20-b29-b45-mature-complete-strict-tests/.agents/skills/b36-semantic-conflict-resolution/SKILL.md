---
name: b36-semantic-conflict-resolution
description: Implement an IDE and PR semantic three-way conflict resolution workflow over base generated latest regenerated and current human-edited target code with policy and validation.
---

# Skill 1297: b36-semantic-conflict-resolution

## Use this skill when

- Incremental migration produces semantic conflicts that cannot be resolved safely by line-based merge.
- Developers need to compare source intent, regeneration, target edits, ownership, and affected contracts.

## Domain-specific risks and invariants

- A conflict UI can silently prefer generated code, discard customer features, or choose unsafe security and transaction changes.
- Resolution must remain reproducible and testable after user edits.

## Workflow

1. Load the common ancestor, latest source-derived target, current human target, semantic diff, ownership, contracts, tests, and risk profile.
2. Classify non-conflicting, conflicting, protected, security, transaction, data, API, and test changes.
3. Present semantic units and evidence rather than only line conflicts; offer deterministic options and explicit manual editing.
4. Record each decision, rationale, approver, and resulting patch.
5. Run affected build, tests, behavior, policy, and regression checks before accepting the resolution.

## Required repository outputs

- `conflicts/profile.json`, conflict session schema, resolution records and replay manifest
- IDE/PR conflict UI or protocol actions, audit trail, validation evidence
- Corpus covering rename, split, merge, target-only feature, security, transaction, and protected-code conflicts

## Verification

- Replay resolutions from immutable inputs.
- Verify no customer-owned or protected code is silently lost.
- Test concurrent resolution, stale branches, rejected options, undo, and PR update.
- Run P0 security, transaction, data, API, and test integrity checks.

## Stop and escalate when

- Security, transaction, money, tenancy, or schema conflicts lack an authorized human decision.
- The common ancestor or source/target artifacts are missing.
- The UI cannot represent a semantic conflict without destructive simplification.
- Post-resolution validation is unavailable or failing.

## Definition of done

- Every critical conflict has an explicit human or certified deterministic decision.
- Resolution is replayable, reviewable, and preserves ownership.
- All required validation passes.
- No silent conflict choice occurs.
