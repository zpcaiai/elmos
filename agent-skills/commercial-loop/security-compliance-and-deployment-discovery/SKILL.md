---
name: security-compliance-and-deployment-discovery
description: "Discover security, compliance, residency, identity, and deployment constraints before commitments. Use when producing or reviewing this Batch 13 commercial capability."
---

# Security Compliance And Deployment Discovery

Read `../references/batch-13-commercial-loop.md` completely before acting.

## Workflow

1. Verify the immutable, signed Batch 12 T-G platform artifact and pin one assessment run and policy version.
2. Read the named external system of record; record missing, stale, conflicting, or unauthorized inputs explicitly.
3. Discover security, compliance, residency, identity, and deployment constraints before commitments. Preserve source identifiers and evidence lineage; never execute CRM, CPQ, contract, billing, payment, tenant, ticket, partner-settlement, or production operations.
4. Produce a security discovery record, required reviews, evidence gaps, prohibitions, and accountable owners. Include status, owner, version, source system, timestamps, evidence references, unknowns, blockers, and next action.
5. Apply the shared lifecycle criteria and submit the result to the orchestrator and final conformance gate.

Do not turn estimates, dashboards, or internal records into evidence of an external commercial operation. Missing or mismatched authority evidence is `NOT_RUN` or blocking, never inferred success.

