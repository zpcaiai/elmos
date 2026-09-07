---
name: github-scm-enterprise-integration-orchestrator
description: "Implement Batch 35A end to end: GitHub Cloud and GHES provider profiles, app registration, installation lifecycle, webhook ingestion, repository synchronization, branch/ref discovery, token brokering, network compatibility, and release gates."
---

# Objective

Implement the complete GitHub SCM asset chain:

approved GitHub provider
→ provider version and capability discovery
→ GitHub App registration
→ tenant-bound installation
→ webhook and periodic reconciliation
→ repository catalog
→ branches, tags, protections, and rules discovery
→ purpose-bound installation token
→ private-runner Git operation
→ access revocation
→ compatibility evidence

# Preconditions

Verify:

- TenantContext;
- RBAC and resource authorization;
- PostgreSQL RLS;
- workload identity for internal services;
- machine-secret reference infrastructure;
- Private Runner identity;
- audit and outbox.

Do not create a parallel Tenant, Repository, Runner, or Audit model.

# Preflight inventory

Search for:

- GitHubWebhookVerifier;
- GitHubAppJwtFactory;
- GitHubInstallationTokenClient;
- repository catalog;
- GitHub installation ID;
- hard-coded `api.github.com`;
- hard-coded `github.com`;
- token persistence;
- `x-access-token`;
- PAT;
- webhook tables;
- branch tables;
- provider configuration;
- TLS verification bypass;
- proxy configuration;
- API version header.

Write:

```text
docs/scm/batch-35a-baseline.md
