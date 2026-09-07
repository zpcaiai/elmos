---
name: application-portfolio-rapid-inventory
description: "Build a rapid, source-referenced application portfolio inventory for commercial estimation. Use when producing or reviewing this Batch 13 commercial capability."
---

# Application Portfolio Rapid Inventory

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Build a rapid, source-referenced application portfolio inventory for commercial estimation. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a deduplicated portfolio inventory, confidence, complexity signals, unknowns, and sampling caveats. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not turn estimates, dashboards, or internal records into evidence of an external commercial operation. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

