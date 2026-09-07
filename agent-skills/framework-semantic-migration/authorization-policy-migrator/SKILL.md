---
name: authorization-policy-migrator
description: "Migrate route, method, role, claim, authority, permission, tenant, ownership, and resource authorization. Use for framework security policy conversion."
---
# Authorization Policy Migrator
Read `../references/afsm-v1.md`. Lift source expressions into an AND/OR/NOT role/claim/permission/authenticated/owner/tenant/time/custom tree before target lowering.

Preserve default deny/allow, method plus route coverage, role/authority distinctions, resource loading order, non-disclosure and 401/403 behavior. Require a target policy for every protected endpoint and permission-matrix tests; block missing conditions or unreviewed custom policy code.

