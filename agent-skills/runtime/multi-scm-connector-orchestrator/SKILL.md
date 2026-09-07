---
name: multi-scm-connector-orchestrator
description: "Implement Batch 35B end to end: a unified SCM contract plus GitLab, Azure DevOps, Bitbucket Cloud, Bitbucket Data Center, and Gitee adapters, webhooks, repository synchronization, Git credential leases, review requests, compatibility tests, and release gates."
---

# Objective

Implement:

unified SCM domain
→ provider registration
→ provider authentication
→ namespace synchronization
→ repository synchronization
→ refs and policy discovery
→ webhook or service-hook registration
→ short-lived or governed credential lease
→ Private Runner Git operation
→ MR/PR creation
→ status publication
→ revocation and reconciliation

# Preconditions

Verify:

- Batch 34 security foundations;
- Batch 35A GitHub provider abstraction;
- common repository catalog;
- Private Runner task contract;
- SecretProvider;
- WorkloadIdentity;
- Outbox;
- Audit;
- Evidence.

Do not create parallel:

- Tenant;
- Repository;
- Snapshot;
- Runner;
- Artifact;
- Review Request;
- Audit;
- Credential Lease

models.

# Preflight

Inventory:

- current ScmProvider types;
- current repository adapter;
- GitHub-only assumptions;
- GitHub-specific fields in core domain;
- token broker;
- Git transport;
- webhook routes;
- review-request model;
- status/check model;
- pagination framework;
- provider error handling;
- rate-limit handling.

Write:

docs/scm/batch-35b-baseline.md

# Implementation order

## Phase 1

Implement unified SCM contracts and migrate GitHub adapter to them without
regressing Batch 35A.

## Phase 2

Implement GitLab Cloud and Self-Managed.

## Phase 3

Implement Azure DevOps Services; add Server compatibility profile.

## Phase 4

Implement Bitbucket Cloud.

## Phase 5

Implement Bitbucket Data Center.

## Phase 6

Implement Gitee.

## Phase 7

Implement unified event normalization, credential coordination, Git
transport, Review Request delivery, and reconciliation.

## Phase 8

Implement provider contract tests and release gates.

# Required logical commits

1. unified-scm-domain-contract
2. github-adapter-migrated-to-unified-contract
3. gitlab-connector
4. azure-devops-connector
5. bitbucket-cloud-connector
6. bitbucket-data-center-connector
7. gitee-connector
8. unified-events-credentials-and-delivery
9. compatibility-tests-and-docs

# Hard stop conditions

Stop and report BLOCKED when:

- repository identity cannot be migrated to provider-native stable IDs;
- a provider requires disabling TLS verification;
- a provider credential must be stored in plaintext;
- provider tokens would need to enter Temporal history;
- a webhook cannot be authenticated at any acceptable assurance level;
- a write capability cannot be safely distinguished from a broad admin
  permission;
- Provider-specific DTOs would have to enter core domain;
- access removal cannot block new Git operations;
- a provider's real test environment is unavailable but the requested result
  requires production verification.

# Completion definition

Batch 35B is complete only when:

- all adapters implement the same domain contract;
- GitHub remains functional;
- every provider uses stable repository identity;
- repository sync and reconciliation work;
- webhooks are verified and idempotent;
- credentials are secret references or ephemeral leases;
- Git operations use typed contracts;
- MR/PR creation is idempotent or reconcilable;
- no provider auto-merges;
- capabilities are truthfully reported;
- verified and fixture-only support are separated;
- release gates pass.

# Completion report

Return:

1. unified connector architecture;
2. provider matrix;
3. authentication matrix;
4. webhook matrix;
5. repository identity matrix;
6. Review Request matrix;
7. token and Git transport;
8. compatibility results;
9. exact commands;
10. files and migrations;
11. unverified capabilities.
