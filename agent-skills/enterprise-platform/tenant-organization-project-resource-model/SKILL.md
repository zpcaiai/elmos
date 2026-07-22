---
name: tenant-organization-project-resource-model
description: Model the tenant, organization, team, project, workspace, repository, run, artifact, and evidence hierarchy. Use when defining resource ownership, inheritance, sharing, movement, or deletion boundaries.
---

# Tenant Organization Project Resource Model

Read `../references/batch-12-enterprise-platform.md`. Produce globally unique opaque IDs, one parent per resource, explicit scoped inheritance, versioned policies and evidence for every share or move. Require `tenant_id` in every non-global resource and maintain a reviewed global-resource allowlist.

Block ambiguous ownership, cross-tenant references and deletion cascades that lack Artifact/Legal Hold review. Feed ownership coverage to T-A.
