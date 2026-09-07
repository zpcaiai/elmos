---
name: organization-hierarchy-domain-claim-and-delegated-administration
description: "Implement tenant organization hierarchy, verified domain claims, workspaces, subtree-scoped delegated administration, hierarchy policies, and cycle prevention."
---

# Objective

Separate these concepts:

Tenant
Organization Unit
Workspace
External Group
Role
Resource Scope

Do not use one table or one external group name for all of them.

# Organization model

```text
Enterprise Tenant
└── Organization Unit
    ├── Business Unit
    ├── Region
    ├── Department
    └── Team Unit

Organization Unit
└── Workspace / Project Space
