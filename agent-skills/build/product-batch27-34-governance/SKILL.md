---
name: product-batch27-34-governance
description: "Build or review ELMOS Product Batches 27-34: TBM, workforce, transformation, control tower, MVP hardening, secure Java vertical loop, and enterprise identity governance. Use when changing the product roadmap catalog, fail-closed gates, persistence, control-plane APIs, or their evidence boundaries."
---

# Product Batch 27-34 Governance

## Read first

- `ChatGPT-Git项目商业化模式 (1).md`
- `docs/product-batches27-34/README.md`
- `modules/product-roadmap-governance/`
- `modules/enterprise-governance/`
- `modules/persistence/src/main/resources/db/migration/V33__technology_business_management.sql` through `V40__enterprise_identity_access_governance.sql`

## Required boundaries

1. Treat these as ELMOS product batches, not Migration Pack Certification M29-M34.
2. Bind every decision to organization, run, immutable snapshot digest and policy version.
3. Keep missing, conflicting, non-independent and future-dated evidence explicit.
4. Return only `BLOCKED` or `READY_FOR_HUMAN_DECISION`; never grant the human decision.
5. Do not execute finance, accounting, employment, production, identity-provider or privileged-access actions.
6. Keep individual workforce data private; prohibit personal ranking and opaque employment decisions.
7. Keep Batch 32 as an independent gap review. Do not import its historical claims as current evidence.
8. Reuse the existing secure Java and enterprise-governance controls for Batches 31, 33 and 34.

## Implementation sequence

1. Update the exact batch catalog, skill/scenario counts and sequential gates.
2. Add or change immutable records and fail-closed evaluation logic.
3. Add tenant-scoped, RLS-protected, append-only migrations.
4. Expose control-plane APIs that prepare human decisions without executing them.
5. Add negative tests for tenant, snapshot, policy, judge independence, evidence completeness and external execution.
6. Run the product module, control-plane, persistence-contract and architecture tests.

## Completion evidence

Report exact commands, test totals, migrations, APIs and unresolved external evidence. Real finance, HR, production, IdP, repository and customer-Runner operations remain `NOT_RUN` until independently observed.
