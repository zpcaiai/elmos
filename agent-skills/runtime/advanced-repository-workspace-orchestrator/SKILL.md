---
name: advanced-repository-workspace-orchestrator
description: "Implement Batch 35C end to end: repository workspace contracts, monorepo slicing, multi-repository products, secure submodules, Git LFS, sparse and partial clone, multi-branch worktrees, enterprise proxy/object cache, cleanup, tests, and release gates."
---

# Objective

Implement this workspace lifecycle:

authorized SCM repositories
→ topology discovery
→ component and repository-set planning
→ branch and commit selection
→ submodule and LFS inventory
→ materialization profile
→ fetch plan
→ workspace creation
→ hydration and integrity verification
→ immutable source snapshot
→ mutable migration worktree
→ verification
→ cleanup and evidence

# Preconditions

Verify:

- unified SCM provider contract;
- stable repository IDs;
- short-lived SCM credential leases;
- Private Runner workload identity;
- per-task sandbox;
- immutable snapshot model;
- artifact/evidence storage;
- Tenant RLS;
- Outbox;
- audit.

Do not create parallel Repository, Snapshot, Runner, Artifact, or SCM
Credential models.

# Preflight inventory

Search for:

- clone and fetch handlers;
- repository snapshot;
- worktree creation;
- branch selection;
- submodule handling;
- LFS handling;
- sparse checkout;
- partial clone;
- Git object cache;
- proxy configuration;
- workspace cleanup;
- disk quota;
- task cancellation.

Write:

```text
docs/scm/batch-35c-baseline.md
