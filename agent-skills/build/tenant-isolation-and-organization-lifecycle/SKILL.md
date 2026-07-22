---
name: tenant-isolation-and-organization-lifecycle
description: Build or review ELMOS organization lifecycle, tenant context derivation, RLS, tenant-scoped cache, storage, events, support grants, and deletion. Use whenever an ELMOS change creates or reads customer-owned objects or crosses organization boundaries.
---

# Tenant Isolation And Organization Lifecycle

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Derive TenantContext only from verified identity plus server-side membership; never trust a body organizationId.
- Require organization_id on every customer object and tenant dimensions in uniqueness, cache keys, object prefixes, messages, search and logs.
- Use application authorization, repository predicates and transaction-scoped PostgreSQL RLS together; missing context fails closed.
- Cover PROVISIONING through DELETED, support grants, encryption context, legal hold and deletion evidence.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Reject cross-tenant reads even when an application query omits its predicate.
- Prove pooled connections do not retain prior tenant settings.
- Prove background jobs without TenantContext fail and legal hold blocks deletion.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

