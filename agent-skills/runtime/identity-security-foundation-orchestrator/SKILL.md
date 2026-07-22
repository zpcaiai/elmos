---
name: identity-security-foundation-orchestrator
description: "Orchestrate implementation of ELMOS OIDC authentication, tenant membership, PostgreSQL RLS, RBAC/ABAC, and cross-tenant security gates. Use for the complete Batch 34A implementation, not for an isolated small bug."
---

# Objective

Replace all development-only tenant shortcuts with an enterprise-grade
authentication and authorization chain:

OIDC identity
→ active tenant membership
→ selected tenant candidate
→ verified tenant context
→ resource authorization
→ PostgreSQL RLS
→ audit evidence

This skill coordinates these implementation skills in order:

1. oidc-bff-resource-server-and-tenant-context
2. tenant-membership-current-tenant-and-lifecycle
3. postgres-role-separation-rls-and-tenant-unit-of-work
4. resource-authorization-rbac-abac-and-audit
5. identity-security-integration-tests-and-release-gates

# Repository assumptions

Expected ELMOS structure:

- apps/control-api
- apps/web
- modules/domain-kernel
- modules/migration-core
- adapters/postgres
- database or Flyway migration directories
- deploy/compose
- root pom.xml
- pnpm workspace

Adapt paths to the actual repository after inspection. Do not create duplicate
modules when an equivalent module already exists.

# Preflight

Before editing:

1. Locate all occurrences of:
   - X-Tenant-Id
   - X-ELMOS-Tenant
   - demo-tenant
   - ELMOS_TENANT_ID
   - tenantId request parameters
   - permitAll
   - securityMatcher
   - postgres superuser credentials
   - POSTGRES_USER
   - set_config
   - current_setting
   - ENABLE ROW LEVEL SECURITY
   - FORCE ROW LEVEL SECURITY

2. Identify:
   - Spring Security configuration;
   - Next.js API proxy routes;
   - user/session implementation;
   - transaction manager;
   - datasource configuration;
   - all tables with tenant_id;
   - audit event writers;
   - Temporal and background jobs using repositories.

3. Run the existing baseline:
   - Java tests;
   - frontend lint;
   - frontend typecheck;
   - current database contract tests.

4. Write a short implementation inventory to:
   docs/security/batch-34a-baseline.md

The inventory must list current vulnerabilities and shortcuts without including
secrets.

# Required implementation order

## Phase 1: domain and schema

Implement:

- FederatedIdentity;
- Tenant;
- TenantMembership;
- Role;
- Permission;
- RoleAssignment;
- ResourceGrant;
- TenantContext;
- AuthorizationDecision.

Add database migrations without deleting historical tenant data.

## Phase 2: authentication

Implement verified OIDC authentication in control-api.

Implement server-side authentication in the Next.js BFF.

Remove direct trust in arbitrary tenant headers.

## Phase 3: tenant membership

Implement current-user and current-tenant APIs.

Require active membership for every tenant selection.

## Phase 4: database isolation

Separate database migration and runtime roles.

Apply RLS to every tenant-scoped table.

Introduce explicit tenant-aware unit of work.

## Phase 5: resource authorization

Enforce permission and resource scope in both:

- API layer;
- application service layer.

Persist authorization decisions for high-risk actions.

## Phase 6: verification

Add real PostgreSQL integration tests and cross-tenant attack tests.

Add startup readiness checks.

# Required commit slices

Prefer these logical commits:

1. identity-domain-and-schema
2. oidc-resource-server-and-web-session
3. tenant-membership-and-selection
4. database-role-separation-and-rls
5. resource-authorization-and-audit
6. security-integration-tests-and-docs

Do not mix broad unrelated refactors into these commits.

# Hard stop conditions

Stop implementation and report BLOCKED when:

- the repository contains no reliable tenant identifier;
- current tenant IDs cannot be migrated without data loss;
- the application cannot use separate Flyway and runtime credentials;
- the available PostgreSQL environment cannot support real RLS tests;
- the selected identity provider metadata is unavailable and no local test
  provider can be configured;
- implementing the requested behavior would require silently weakening an
  existing authorization rule.

# Completion definition

Batch 34A is complete only when:

- unauthenticated requests are rejected;
- arbitrary tenant headers cannot cross tenant boundaries;
- active membership is required;
- repository/project resources are separately authorized;
- runtime database role is non-superuser and non-owner;
- all tenant tables use RLS;
- a missing tenant context fails closed;
- cross-tenant read and write tests fail as expected;
- frontend no longer injects demo tenant identity;
- authorization decisions are auditable;
- Java and frontend production builds pass.

# Completion report

Return:

1. current authentication flow;
2. current tenant resolution flow;
3. current database role model;
4. authorization model;
5. test matrix and results;
6. removed insecure shortcuts;
7. unresolved limitations;
8. files changed.
