---
name: differential-evidence-and-reproduction-package-builder
description: "Build immutable, redacted Batch 9 evidence and reproduction packages for differences and gates. Use for triage, review, repair handoff or delivery acceptance."
---

# Differential Evidence and Reproduction Package Builder

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Bundle fixed Snapshots, environment, input, initial state, raw/canonical observations and diffs.
2. Include rules, clock, seed, external recordings, collector state, root cause and sandbox commands.
3. Link comparisons, obligations, patches and final module gates.

## Hard rules

- Do not use screenshots as the only evidence.
- Lock dynamic versions and never overwrite a prior package.
- Mark collector failure and scan every export for secrets.

## Output

Emit independently reproducible machine-readable packages and report references.

