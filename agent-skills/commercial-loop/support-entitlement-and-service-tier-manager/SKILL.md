---
name: support-entitlement-and-service-tier-manager
description: "Reconcile support entitlements and service tiers against contract and subscription authority. Use when producing or reviewing this Batch 13 commercial capability."
---

# Support Entitlement And Service Tier Manager

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Reconcile support entitlements and service tiers against contract and subscription authority. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce an entitlement decision, effective period, limits, conflicts, evidence, and correction owner. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not pass unsupported SLA promises, unowned P1 failures, missing interventions, or unconsented claims. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

