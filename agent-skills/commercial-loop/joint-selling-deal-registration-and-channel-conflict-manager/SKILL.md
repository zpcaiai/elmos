---
name: joint-selling-deal-registration-and-channel-conflict-manager
description: "Govern deal registration, joint selling, attribution, expiry, and channel conflict resolution. Use when producing or reviewing this Batch 13 commercial capability."
---

# Joint Selling Deal Registration And Channel Conflict Manager

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Govern deal registration, joint selling, attribution, expiry, and channel conflict resolution. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a registered deal decision, ownership, protected period, conflicts, approvals, and audit references. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not turn estimates, dashboards, or internal records into evidence of an external commercial operation. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

