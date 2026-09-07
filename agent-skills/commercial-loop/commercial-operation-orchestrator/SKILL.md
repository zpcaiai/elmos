---
name: commercial-operation-orchestrator
description: "Coordinate the evidence-bound lifecycle across all eight commercial domains. Use when producing or reviewing this Batch 13 commercial capability."
---

# Commercial Operation Orchestrator

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Coordinate the evidence-bound lifecycle across all eight commercial domains. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a lifecycle decision, sequential B13-A through B13-G gate result, and consolidated blocker register. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not turn estimates, dashboards, or internal records into evidence of an external commercial operation. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

