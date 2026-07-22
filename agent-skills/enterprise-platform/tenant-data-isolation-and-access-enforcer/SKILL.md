---
name: tenant-data-isolation-and-access-enforcer
description: Enforce tenant context in databases, object storage, search, cache, messaging, exports, and background jobs. Use when reviewing or designing server-side tenant data boundaries.
---

# Tenant Data Isolation and Access Enforcer

Read `../references/batch-12-enterprise-platform.md`. Require server-established tenant, organization, actor and policy context; inject database/Search filters server-side, namespace caches, authorize object paths and restore context in jobs. Test CRUD, search, cache, export and administrator flows negatively across tenants.

Missing context, client-controlled filters or any cross-tenant result is a Critical T-A blocker.
