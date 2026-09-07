---
name: nondeterministic-diff-and-flakiness-detector
description: "Detect and classify unstable Batch 9 differences caused by source, target, environment, collector, time, random or concurrency behavior. Use when repeated clean runs disagree."
---

# Nondeterministic Diff and Flakiness Detector

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Repeat identical snapshots, inputs and controls and fingerprint canonical outcomes.
2. Vary only one suspected nondeterministic dimension at a time.
3. Classify source, target, both, environment, collector, true race or unknown instability.

## Hard rules

- Retry-then-pass never becomes stable equivalent.
- Do not ignore every unstable field.
- Keep target-only nondeterminism and concurrency races blocking until governed.

## Output

Emit flaky records, rates, differing fields and reproduction evidence.

