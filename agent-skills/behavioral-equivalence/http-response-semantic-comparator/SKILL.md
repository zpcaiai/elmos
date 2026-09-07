---
name: http-response-semantic-comparator
description: "Compare Batch 9 HTTP status, headers, cookies, body presence and values, streaming and protocol semantics. Use for public endpoint differential validation."
---

# HTTP Response Semantic Comparator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Classify business, security and infrastructure headers.
2. Compare JSON presence, null, empty, numeric type, Decimal, enum, Unicode, objects and ordered arrays.
3. Compare stream chunks, boundaries, flush behavior, midstream error and cancellation.

## Hard rules

- Never merge 200 with 204 or 401 with 403.
- Never sort arrays or merge missing with null without contract proof.
- Compare secure cookie and security-header attributes.

## Output

Emit raw and canonical HTTP diffs with contract-level severity.

