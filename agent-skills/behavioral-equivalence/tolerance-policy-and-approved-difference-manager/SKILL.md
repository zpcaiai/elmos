---
name: tolerance-policy-and-approved-difference-manager
description: "Govern scoped Batch 9 numerical/time tolerances, temporary waivers and approved behavior changes. Use when a non-exact result may be contractually acceptable."
---

# Tolerance Policy and Approved Difference Manager

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Bind tolerance to one scenario, observation, field, value, rationale, approver, evidence and expiry.
2. Record approved change business reason, compatibility/version strategy, callers, tests, release and rollback.
3. Keep equivalent, within-tolerance, approved-change and waived states separate.

## Hard rules

- Never let an Agent approve or widen a rule.
- Forbid tolerance for money, permissions, status, counts, transactions, audit and tenant isolation.
- Do not rewrite a Golden to match an error.

## Output

Emit auditable decisions, expiry alerts and contract/report updates.

