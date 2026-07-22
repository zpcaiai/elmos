---
name: qbr-and-value-realization-manager
description: "Prepare QBR and value realization evidence against agreed baselines and outcomes. Use when producing or reviewing this Batch 13 commercial capability."
---

# Qbr And Value Realization Manager

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Prepare QBR and value realization evidence against agreed baselines and outcomes. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a QBR packet with adoption, outcomes, gaps, actions, owners, dates, and customer acknowledgement. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not pass unsupported SLA promises, unowned P1 failures, missing interventions, or unconsented claims. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

