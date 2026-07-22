---
name: elmos-domain-model
description: Design or change ELMOS aggregates, value objects, immutable snapshots and evidence references, domain events, repositories, tenant invariants, approval rules, and optimistic versions. Use for Organization, Repository, Snapshot, Assessment, MigrationPlan, MigrationRun, StepRun, Evidence, Finding, or domain-event work.
---

# ELMOS Domain Model

## 适用与边界

Use for ELMOS domain behavior. Keep this module framework-free and do not place controller, SQL, HTTP, or Agent code here.

## 核心不变量

1. Bind every scan, migration, and validation to an immutable RepositorySnapshot.
2. Require baseline results before migration.
3. Make an approved MigrationPlan immutable; create a new version for changes.
4. Require approval before high-risk execution.
5. Require at least one Evidence ID before a Step succeeds.
6. Prevent Agents and controllers from declaring final success.
7. Let ValidationPolicy decide success.
8. Prevent cross-organization references.
9. Keep published Evidence and audit history immutable.
10. Produce a domain event for every important transition.

## 实现步骤

1. Identify the aggregate that owns the invariant.
2. Express identity, commits, versions, scores, budgets, and artifact references as explicit types.
3. Keep fields private or immutable; expose behavior methods instead of public setters.
4. Inject Clock and ID generation at construction boundaries.
5. reject illegal transitions with a domain exception.
6. Return domain events for transactional Outbox storage.
7. Test happy paths, illegal transitions, retry/idempotency, optimistic conflicts, and tenant isolation.

## 输入输出与验收

Take the requested behavior, current aggregate state, tenant, plan version, and evidence references. Output domain code, events, repository Port changes if needed, and tests. Accept only when the domain module has no framework dependency and every new invariant is directly tested. Preserve the failing state and escalate ambiguous business semantics instead of inventing them.

