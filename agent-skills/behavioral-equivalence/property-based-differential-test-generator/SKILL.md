---
name: property-based-differential-test-generator
description: "Generate and shrink schema-valid Batch 9 source-target property tests. Use for broad boundary, Unicode, null, collection, time, numeric and structural input exploration."
---

# Property Based Differential Test Generator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Define a domain-supported property and required observations.
2. Generate boundary-weighted cases with a recorded seed and safe operation scope.
3. Run both systems, shrink failures without changing the failure class and save the minimum counterexample.

## Hard rules

- Do not test only the target or generate dangerous real operations.
- Use exact financial boundaries.
- Route suspected source bugs to review rather than adopting target behavior.

## Output

Emit generators, seeds, pass rates and replayable minimal counterexamples.

