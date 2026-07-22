---
name: behavior-difference-diagnostic-agent
description: "Use a constrained Agent to diagnose complex Batch 9 differences and propose evidence, tests or Batch 8 repair candidates. Use only after deterministic comparison and clustering leave an evidenced gap."
---

# Behavior Difference Diagnostic Agent

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Provide the minimum redacted scenario, observations, diffs, mappings, code slices and obligations.
2. Ask for ranked causes, missing observations, minimal reproductions, test ideas and bounded repair candidates.
3. Validate every proposal through an independent Oracle, test or human review.

## Hard rules

- Never let the Agent approve a difference, tolerance or Golden.
- Never let it delete observation points, close obligations or edit high-risk code directly.
- Return unknown when evidence is insufficient.

## Output

Emit structured, provenance-linked diagnostic candidates with mandatory review.

