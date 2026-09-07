---
name: multi-repository-product-composition-lockfile-consisten-2735e221
description: "Implement Multi-repository Product composition, repository-set manifests, exact-commit lockfiles, cross-repository dependency graph, consistency rules, synchronized snapshots, coordinated migration changes, delivery order, and product-level evidence."
---

# Objective

Represent a logical Product whose code is distributed across multiple SCM
repositories and possibly multiple providers.

# Domain model

Create:

```text
workspace.products
workspace.product_versions
workspace.product_repository_sets
workspace.product_repository_set_versions
workspace.product_repository_members
workspace.product_repository_roles
workspace.product_repository_dependencies
workspace.product_commit_selection_rules
workspace.product_snapshot_plans
workspace.product_snapshots
workspace.product_snapshot_members
workspace.product_lock_manifests
workspace.product_consistency_rules
workspace.product_consistency_results
workspace.product_change_sets
workspace.product_change_set_members
workspace.product_delivery_dependencies
workspace.product_evidence_packs
