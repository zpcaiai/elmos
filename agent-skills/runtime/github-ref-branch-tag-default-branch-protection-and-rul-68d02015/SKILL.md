---
name: github-ref-branch-tag-default-branch-protection-and-rul-68d02015
description: "Implement versioned discovery of Git refs, branches, tags, default branch, maintained-branch policies, branch protection, repository/organization rulesets, force updates, and migration branch-selection evidence without mutating customer policy."
---

# Objective

Provide an accurate multi-branch model for assessment and migration planning.

Batch 35A is read-only for branch protection and rulesets.

# Domain model

Create:

```text
catalog.repository_refs
catalog.repository_ref_versions
catalog.repository_branches
catalog.repository_branch_versions
catalog.repository_tags
catalog.repository_tag_versions
catalog.repository_default_branch_history
catalog.repository_branch_protections
catalog.repository_rulesets
catalog.repository_ruleset_versions
catalog.repository_effective_branch_rules
catalog.repository_branch_selection_policies
catalog.repository_branch_classifications
catalog.repository_ref_events
catalog.repository_ref_reconciliation_runs
