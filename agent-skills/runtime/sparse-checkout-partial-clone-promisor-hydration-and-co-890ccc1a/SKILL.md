---
name: sparse-checkout-partial-clone-promisor-hydration-and-co-890ccc1a
description: "Implement Sparse Checkout and Partial Clone profiles, cone/non-cone governance, sparse-index compatibility, provider filter probing, promisor-remote validation, explicit hydration, offline preparation, sparse drift detection, and task-completeness verification."
---

# Objective

Reduce Monorepo transfer and checkout cost without hiding missing source or
causing uncontrolled network access.

# Domain model

Create:

```text
workspace.sparse_profiles
workspace.sparse_profile_versions
workspace.sparse_specifications
workspace.sparse_paths
workspace.sparse_materialization_runs
workspace.sparse_drift_findings
workspace.partial_clone_profiles
workspace.partial_clone_capability_results
workspace.promisor_remotes
workspace.promised_objects
workspace.object_hydration_plans
workspace.object_hydration_runs
workspace.object_hydration_events
workspace.offline_preparation_runs
workspace.git_tool_compatibility_profiles
workspace.sparse_partial_findings
