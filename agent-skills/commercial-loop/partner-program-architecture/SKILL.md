---
name: partner-program-architecture
description: "Define partner types, levels, benefits, obligations, economics, certification, and controls. Use when producing or reviewing this Batch 13 commercial capability."
---

# Partner Program Architecture

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Define partner types, levels, benefits, obligations, economics, certification, and controls. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a versioned partner program with entry and exit criteria, governance, boundaries, and owners. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not pass uncertified delivery, overbroad access, channel ambiguity, or unreconciled settlement. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

