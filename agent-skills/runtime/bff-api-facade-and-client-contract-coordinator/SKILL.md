---
name: bff-api-facade-and-client-contract-coordinator
description: Coordinate Web, desktop, and mobile BFF/API facade aggregation, DTO projection, version adaptation, authentication context, error mapping, caching, and compatibility windows. Use for client-backend contract migration.
---

# BFF and Client Contract Coordination

## Workflow

1. Inventory each client contract, active version, platform, BFF operation, backend operation, auth/session context, errors, caching, rate limits, timeouts, and removal date.
2. Select versioned endpoint, header/capability version, optional field, upcast/downcast, flag, or legacy facade explicitly.
3. Preserve user, tenant, device, claims, CSRF, refresh, logout, rotation, and correlation semantics end to end.
4. Test aggregation, partial failure, timeout, retry, cache staleness, rate limits, and every active old/new client/BFF/backend combination.
5. Give compatibility code an owner, expiry, usage observation, and removal task.

## Gates

Block core business rules, transaction ownership, cross-domain transactions, shared super-identity, lost authorization context, undefined partial failure, unknown active client versions, and unobservable compatibility code.

## Output

Emit client/BFF contracts, version matrix, auth/error mappings, compatibility plan, contract results, removal gates, and Evidence.
