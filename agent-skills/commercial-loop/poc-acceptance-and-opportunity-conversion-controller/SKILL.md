---
name: poc-acceptance-and-opportunity-conversion-controller
description: "Control POC acceptance and opportunity conversion using signed success criteria. Use when producing or reviewing this Batch 13 commercial capability."
---

# Poc Acceptance And Opportunity Conversion Controller

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Control POC acceptance and opportunity conversion using signed success criteria. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce an acceptance decision, deviations, residual risks, commercial next step, and authoritative references. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not pass hidden failures, unmeasured success criteria, or unsupported automation claims. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

