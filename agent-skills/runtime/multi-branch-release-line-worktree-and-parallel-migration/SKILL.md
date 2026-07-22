---
name: multi-branch-release-line-worktree-and-parallel-migration
description: "Implement branch-family and release-line modeling, exact-commit selection, isolated Git worktrees, branch leases, parallel migration scheduling, deterministic per-branch rewrites, divergence analysis, stacked delivery, cleanup, and recovery."
---

# Objective

Safely modernize repositories that maintain:

- main;
- release branches;
- long-term support branches;
- customer-specific branches;
- hotfix branches;
- vendor branches.

# Domain model

Create:

```text
workspace.branch_families
workspace.branch_family_versions
workspace.release_lines
workspace.release_line_versions
workspace.branch_memberships
workspace.branch_selection_runs
workspace.branch_baselines
workspace.branch_divergence_results
workspace.branch_migration_plans
workspace.branch_worktrees
workspace.branch_worktree_leases
workspace.branch_worktree_locks
workspace.branch_patch_sets
workspace.cross_branch_consistency_rules
workspace.branch_delivery_sets
workspace.worktree_reconciliation_runs
