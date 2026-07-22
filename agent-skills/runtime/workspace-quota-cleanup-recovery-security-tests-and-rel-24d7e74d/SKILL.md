---
name: workspace-quota-cleanup-recovery-security-tests-and-rel-24d7e74d
description: "Implement Workspace quotas, reservations, lifecycle reapers, Git-aware cleanup, crash recovery, orphan reconciliation, malicious repository fixtures, Monorepo/Submodule/LFS/Sparse/Partial/Worktree/cache tests, metrics, evidence, and mandatory release gates."
---

# Objective

Prove advanced Repository Workspaces remain isolated, reproducible, bounded,
and recoverable under failures and malicious Repository content.

# Quota model

Create:

```text
workspace.quota_profiles
workspace.quota_assignments
workspace.resource_reservations
workspace.resource_usage_observations
workspace.quota_violations
workspace.workspace_reaper_runs
workspace.orphan_workspace_findings
workspace.cleanup_tasks
workspace.cleanup_attempts
workspace.recovery_runs
workspace.security_test_runs
workspace.release_gate_results
