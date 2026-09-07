---
name: behavior-regression-corpus-promoter
description: "Promote stable Batch 9 Goldens, boundaries, counterexamples, incidents and repaired regressions into permanent test corpora. Use after source behavior and the repair are reviewed."
---

# Behavior Regression Corpus Promoter

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Verify sanitized input, stable reproduction, trusted source behavior, explicit Oracles and complete observations.
2. Deduplicate and assign fast, module, contract, integration, nightly or release-gate layers.
3. Version applicability and preserve origin, criticality and maintenance state.

## Hard rules

- Never promote flaky, unreviewed Golden or unresolved source-bug behavior.
- Keep high-cost cases out of fast layers.
- Require a reason and evidence for retirement.

## Output

Emit searchable regression-case records linked to rules, modules and evidence.

