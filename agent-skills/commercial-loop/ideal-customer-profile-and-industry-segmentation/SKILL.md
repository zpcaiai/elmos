---
name: ideal-customer-profile-and-industry-segmentation
description: "Define versioned ideal-customer profiles and evidence-backed industry segments. Use when producing or reviewing this Batch 13 commercial capability."
---

# Ideal Customer Profile And Industry Segmentation

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Define versioned ideal-customer profiles and evidence-backed industry segments. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce an ICP version, inclusion and exclusion rules, segment evidence, owner, and review date. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not turn estimates, dashboards, or internal records into evidence of an external commercial operation. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

