---
name: github-repository-catalog-sync-authorization-and-reconciliation
description: "Implement installation repository inventory, stable repository identity, metadata snapshots, permission state, rename/transfer/archive/delete lifecycle, import authorization, pagination, conditional requests, and periodic reconciliation."
---

# Objective

Build a trustworthy repository catalog from GitHub Installation authority.

Webhook state and UI names are not sufficient.

# Domain model

Create or extend:

```text
catalog.scm_repositories
catalog.scm_repository_versions
catalog.github_repository_metadata
catalog.github_repository_permissions
catalog.github_repository_installations
catalog.repository_authorizations
catalog.repository_sync_runs
catalog.repository_sync_pages
catalog.repository_reconciliation_findings
catalog.repository_tombstones
catalog.repository_aliases
catalog.repository_relationships
