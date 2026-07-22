---
name: golden-master-registry-and-version-manager
description: "Capture, review, version, invalidate and supersede Batch 9 Golden Master behavior packages. Use when establishing or updating a trusted source baseline."
---

# Golden Master Registry and Version Manager

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Bind input, initial state, environment, raw/canonical observations, rules and source Snapshot.
2. Move Golden candidates through explicit human review and approval.
3. Invalidate on source bug, contract, flag, schema, input, clock, recording or rule change.

## Hard rules

- Never generate a Golden from target output.
- Never overwrite raw history or silently copy an unreviewed source bug.
- Treat updates like reviewed code changes with rollback.

## Output

Emit immutable Golden versions, diffs, approval and supersession links.

