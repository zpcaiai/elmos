---
name: risk-contingency-and-uncertainty-pricing
description: "Price explicit delivery and commercial uncertainty without hiding risk in opaque buffers. Use when producing or reviewing this Batch 13 commercial capability."
---

# Risk Contingency And Uncertainty Pricing

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Price explicit delivery and commercial uncertainty without hiding risk in opaque buffers. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a risk register linked to contingency, trigger, owner, approval, and customer-visible assumption. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not pass scope, SOW, quote, contract, discount, margin, acceptance, or billing mismatches. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

