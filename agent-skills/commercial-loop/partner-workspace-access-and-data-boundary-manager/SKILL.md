---
name: partner-workspace-access-and-data-boundary-manager
description: "Control partner workspace access, tenant boundaries, data classification, purpose, and expiry. Use when producing or reviewing this Batch 13 commercial capability."
---

# Partner Workspace Access And Data Boundary Manager

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Control partner workspace access, tenant boundaries, data classification, purpose, and expiry. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce an access decision with least privilege, approvals, boundary evidence, monitoring, and revocation. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not pass uncertified delivery, overbroad access, channel ambiguity, or unreconciled settlement. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

