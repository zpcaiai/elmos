---
name: repository-workspace-contract-manifest-and-lifecycle
description: "Implement provider-neutral Repository Workspace contracts, immutable manifests, materialization and hydration states, source/worktree separation, leases, lifecycle, APIs, audit, and evidence."
---

# Objective

Represent exactly what source material exists inside every Runner workspace.

# Domain model

Create:

```text
workspace.repository_workspaces
workspace.repository_workspace_versions
workspace.workspace_sources
workspace.workspace_source_versions
workspace.workspace_materialization_profiles
workspace.workspace_materialization_runs
workspace.workspace_paths
workspace.workspace_objects
workspace.workspace_missing_objects
workspace.workspace_leases
workspace.workspace_locks
workspace.workspace_integrity_results
workspace.workspace_cleanup_runs
workspace.workspace_manifests
workspace.workspace_manifest_artifacts
workspace.workspace_events
