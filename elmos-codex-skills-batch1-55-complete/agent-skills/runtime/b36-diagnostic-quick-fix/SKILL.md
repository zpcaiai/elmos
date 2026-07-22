---
name: b36-diagnostic-quick-fix
description: "Implement safe diagnostic quick fixes and local repair actions that bind to exact diagnostics artifacts policies ownership and tests and never apply broad speculative edits."
---

# Skill 1296: b36-diagnostic-quick-fix

## Use this skill when

- IDE or CLI users need fast fixes for known diagnostics.
- Certified deterministic repair recipes should be available at the point of failure.

## Domain-specific risks and invariants

- Stale diagnostics, broad edits, unsafe dependencies, weakened tests, and unverified agent patches can corrupt target code.
- Quick fixes can bypass Batch 24 repair policy if implemented separately.

## Workflow

1. Reuse Batch 24 diagnostic, root-cause, repair-policy, recipe, patch, and test-integrity contracts.
2. Advertise quick fixes only when preconditions, document versions, artifact digests, ownership, and policy decisions match.
3. Generate previewable minimal patches with expected diagnostic delta and required tests.
4. Apply through safe host APIs with undo or through atomic CLI/PR patches.
5. Run parse, format, build, static, focused-test, policy, and integrity validation before acceptance.

## Required repository outputs

- `quick-fix/profile.json`, quick-fix registry and generated IDE/CLI actions
- Patch previews, policy decisions, test evidence, rollback and stale-diagnostic tests
- Acceptance and rejection telemetry without source content

## Verification

- Test stale diagnostics, concurrent edits, protected regions, high-risk security/transaction changes, dependency additions, and failing postconditions.
- Verify rejected or failed fixes leave the workspace unchanged.
- Run holdout diagnostics not used to create the recipes.
- Verify quick-fix results match Batch 24 repair-loop behavior.

## Stop and escalate when

- The fix requires changing tests, security, transactions, money, schema, or public APIs without approval.
- Document or artifact freshness cannot be proven.
- No deterministic or approved bounded repair plan exists.
- Required validation cannot run locally or remotely.

## Definition of done

- Only evidence-supported fixes are offered.
- Patches are minimal, reviewable, undoable, and policy-compliant.
- Required tests pass and no higher-severity issue is introduced.
- Stale or unsafe actions fail closed.
