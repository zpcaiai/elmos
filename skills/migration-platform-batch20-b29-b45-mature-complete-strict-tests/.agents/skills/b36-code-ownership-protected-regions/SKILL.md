---
name: b36-code-ownership-protected-regions
description: Implement durable code ownership protected regions generated/manual boundaries extension points and overwrite prevention across IDE CLI bots regeneration and merges.
---

# Skill 1298: b36-code-ownership-protected-regions

## Use this skill when

- Generated code must coexist with long-lived customer-maintained target code.
- Editors, CLI, PR bots, and generators need one shared ownership policy.

## Domain-specific risks and invariants

- Comment-only markers can drift, generated files may be hand-edited, and multiple tools can interpret ownership differently.
- Incorrect ownership can destroy customer work or prevent necessary security fixes.

## Workflow

1. Define ownership at repository path, file, type, member, region, contract, and test levels.
2. Support platform-owned, customer-owned, shared, generated-once, protected, and deprecated states with regeneration and review policies.
3. Persist ownership in typed metadata and integrate with source maps, code owners, IDE UI, generators, merge, quick fixes, and PR checks.
4. Implement migration of ownership metadata when symbols move, split, merge, or are renamed.
5. Add overwrite, deletion, stale metadata, forged marker, conflicting owner, and emergency security-fix tests.

## Required repository outputs

- `ownership/policy.json`, ownership metadata/index, generated markers or sidecar files
- Overwrite-prevention tests, ownership migration evidence, CODEOWNERS integration
- User-visible ownership explanations and change-review flow

## Verification

- Validate every generated or modified P0 symbol has ownership.
- Attempt unauthorized overwrite, deletion, rename, merge, and quick-fix actions.
- Verify policy is consistent across generator, IDE, CLI, and PR bot.
- Test emergency override with approval, audit, expiry, and rollback.

## Stop and escalate when

- Ownership is ambiguous for a proposed write.
- The only boundary is an untrusted editable comment.
- A customer-owned or protected region would be overwritten without approval.
- Ownership migration after rename/split/merge cannot be proven.

## Definition of done

- Protected-code overwrites are zero.
- All write paths enforce the same ownership policy.
- Ownership changes are auditable and versioned.
- Developers can safely maintain target code between regenerations.
