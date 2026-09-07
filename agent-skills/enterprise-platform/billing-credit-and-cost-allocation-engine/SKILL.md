---
name: billing-credit-and-cost-allocation-engine
description: Reproduce subscription, seat, repository, run, usage, reservation, private-license, support, credit, discount, and cost-allocation charges from immutable usage. Use for invoice or reconciliation logic.
---

# Billing Credit and Cost Allocation Engine

Read `../references/batch-12-enterprise-platform.md`. Snapshot versioned price rules at occurrence time, allocate by tenant/org/project/cost center/repo/run/pool/model and trace every charge or credit to Ledger/Meter facts. Keep tax outside product logic and approve manual credits.

Billing admins cannot mutate usage. Any duplicate charge or reconciliation difference above policy blocks T-D.
