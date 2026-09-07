---
name: enterprise-rbac-model
description: Define least-privilege platform, tenant, organization, project, workspace, and resource roles and permissions. Use for RBAC matrices, scope inheritance, sensitive permissions, or access reviews.
---

# Enterprise RBAC Model

Read `../references/batch-12-enterprise-platform.md`. Map every API action to an explicit permission and scope; separate source access, migration execution, approval, Runner, model policy, secret, billing, audit and Break-glass powers. Keep Platform and tenant roles disjoint and make revocation immediate.

Hidden broad Admin grants, Auditor mutation or Tenant Admin platform privilege are T-B blockers.
