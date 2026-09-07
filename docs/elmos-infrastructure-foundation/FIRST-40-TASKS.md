# First 40 Implementation Tasks

This is the recommended first dependency-resolved backlog. Reorder only after repository discovery proves an existing capability or a hard dependency.

## 1. `ELMOS-ARCH-001`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture inventory  
**Priority/Phase:** `P0` / `G0`

Inventory each module, entry point, dependency, persistent state, network endpoint, and deployment mode.

Acceptance hint: Implement and verify: Inventory each module, entry point, dependency, persistent state, network endpoint, and deployment mode.

## 2. `ELMOS-ARCH-002`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture inventory  
**Priority/Phase:** `P0` / `G0`

Draw control, workflow, execution, artifact, model, policy, evidence, data, and observability planes.

Acceptance hint: Implement and verify: Draw control, workflow, execution, artifact, model, policy, evidence, data, and observability planes.

## 3. `ELMOS-ARCH-003`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture inventory  
**Priority/Phase:** `P0` / `G0`

Assign one authoritative owner for every core state domain.

Acceptance hint: Implement and verify: Assign one authoritative owner for every core state domain.

## 4. `ELMOS-ARCH-004`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture inventory  
**Priority/Phase:** `P0` / `G0`

Find process-local state that would be lost on restart and assign a durable store.

Acceptance hint: Implement and verify: Find process-local state that would be lost on restart and assign a durable store.

## 5. `ELMOS-ARCH-005`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture inventory  
**Priority/Phase:** `P0` / `G0`

Mark modules that remain inside the modular monolith and justified independent workers.

Acceptance hint: Implement and verify: Mark modules that remain inside the modular monolith and justified independent workers.

## 6. `ELMOS-ARCH-006`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture decisions  
**Priority/Phase:** `P0` / `G0`

Write an ADR for Temporal versus a custom workflow engine.

Acceptance hint: Implement and verify: Write an ADR for Temporal versus a custom workflow engine.

## 7. `ELMOS-ARCH-007`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture decisions  
**Priority/Phase:** `P0` / `G0`

Write an ADR for content-addressed storage versus project copying.

Acceptance hint: Implement and verify: Write an ADR for content-addressed storage versus project copying.

## 8. `ELMOS-ARCH-008`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture decisions  
**Priority/Phase:** `P0` / `G0`

Write an ADR for private-runner source residency.

Acceptance hint: Implement and verify: Write an ADR for private-runner source residency.

## 9. `ELMOS-ARCH-009`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture decisions  
**Priority/Phase:** `P0` / `G0`

Write an ADR for deterministic rules before LLM repair.

Acceptance hint: Implement and verify: Write an ADR for deterministic rules before LLM repair.

## 10. `ELMOS-ARCH-010`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture decisions  
**Priority/Phase:** `P0` / `G0`

Write an ADR for event-plane responsibilities and why it does not replace workflows.

Acceptance hint: Implement and verify: Write an ADR for event-plane responsibilities and why it does not replace workflows.

## 11. `ELMOS-ARCH-011`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Architecture decisions  
**Priority/Phase:** `P0` / `G0`

Define ADR states proposed, accepted, superseded, rejected, and deprecated.

Acceptance hint: Implement and verify: Define ADR states proposed, accepted, superseded, rejected, and deprecated.

## 12. `ELMOS-ARCH-012`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Identifiers and states  
**Priority/Phase:** `P0` / `G0`

Standardize tenant, user, repository, snapshot, project, workflow, task, attempt, runner, artifact, evidence, approval, and policy identifiers.

Acceptance hint: Implement and verify: Standardize tenant, user, repository, snapshot, project, workflow, task, attempt, runner, artifact, evidence, approval, and policy identifiers.

## 13. `ELMOS-ARCH-013`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Identifiers and states  
**Priority/Phase:** `P0` / `G0`

Replace free-form status strings with versioned enums.

Acceptance hint: Implement and verify: Replace free-form status strings with versioned enums.

## 14. `ELMOS-ARCH-014`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Identifiers and states  
**Priority/Phase:** `P0` / `G0`

Define allowed state transitions and terminal states.

Acceptance hint: Implement and verify: Define allowed state transitions and terminal states.

## 15. `ELMOS-ARCH-015`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Identifiers and states  
**Priority/Phase:** `P0` / `G0`

Define idempotency key, receipt, transition ID, fencing token, correlation ID, trace ID, and audit ID formats.

Acceptance hint: Implement and verify: Define idempotency key, receipt, transition ID, fencing token, correlation ID, trace ID, and audit ID formats.

## 16. `ELMOS-ARCH-016`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** Identifiers and states  
**Priority/Phase:** `P0` / `G0`

Add database uniqueness and transition constraints.

Acceptance hint: Implement and verify: Add database uniqueness and transition constraints.

## 17. `ELMOS-ARCH-017`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** API and schema governance  
**Priority/Phase:** `P0` / `G0`

Version external APIs under /api/v1 and define deprecation policy.

Acceptance hint: Implement and verify: Version external APIs under /api/v1 and define deprecation policy.

## 18. `ELMOS-ARCH-018`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** API and schema governance  
**Priority/Phase:** `P0` / `G0`

Define a uniform error envelope with code, message, retryable, correlation_id, and details.

Acceptance hint: Implement and verify: Define a uniform error envelope with code, message, retryable, correlation_id, and details.

## 19. `ELMOS-ARCH-019`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** API and schema governance  
**Priority/Phase:** `P0` / `G0`

Define pagination, filtering, sorting, ETag, conditional update, and idempotency semantics.

Acceptance hint: Implement and verify: Define pagination, filtering, sorting, ETag, conditional update, and idempotency semantics.

## 20. `ELMOS-ARCH-020`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** API and schema governance  
**Priority/Phase:** `P0` / `G0`

Add schema_version to every cross-module DTO and event.

Acceptance hint: Implement and verify: Add schema_version to every cross-module DTO and event.

## 21. `ELMOS-ARCH-021`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** API and schema governance  
**Priority/Phase:** `P0` / `G0`

Generate clients from OpenAPI and bindings from Protobuf.

Acceptance hint: Implement and verify: Generate clients from OpenAPI and bindings from Protobuf.

## 22. `ELMOS-ARCH-022`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** API and schema governance  
**Priority/Phase:** `P0` / `G0`

Reject removed required fields, reused Protobuf numbers, and incompatible enum changes in CI.

Acceptance hint: Implement and verify: Reject removed required fields, reused Protobuf numbers, and incompatible enum changes in CI.

## 23. `ELMOS-ARCH-023`

**Skill:** `elmos-architecture-contract-governance`  
**Group:** API and schema governance  
**Priority/Phase:** `P0` / `G0`

Adopt canonical repository directories and ownership rules.

Acceptance hint: Implement and verify: Adopt canonical repository directories and ownership rules.

## 24. `ELMOS-SEC-001`

**Skill:** `elmos-identity-tenant-security`  
**Group:** OIDC and sessions  
**Priority/Phase:** `P0` / `G1`

Add an OIDC resource server and validate issuer, audience, expiration, signature algorithm, nonce where applicable, and token type.

Acceptance hint: Implement and verify: Add an OIDC resource server and validate issuer, audience, expiration, signature algorithm, nonce where applicable, and token type.

## 25. `ELMOS-SEC-002`

**Skill:** `elmos-identity-tenant-security`  
**Group:** OIDC and sessions  
**Priority/Phase:** `P0` / `G1`

Resolve user only from validated token or server-side session.

Acceptance hint: Implement and verify: Resolve user only from validated token or server-side session.

## 26. `ELMOS-SEC-003`

**Skill:** `elmos-identity-tenant-security`  
**Group:** OIDC and sessions  
**Priority/Phase:** `P0` / `G1`

Resolve active tenant from validated membership, never arbitrary headers.

Acceptance hint: Implement and verify: Resolve active tenant from validated membership, never arbitrary headers.

## 27. `ELMOS-SEC-004`

**Skill:** `elmos-identity-tenant-security`  
**Group:** OIDC and sessions  
**Priority/Phase:** `P0` / `G1`

Support multi-tenant membership and authorized tenant selection.

Acceptance hint: Implement and verify: Support multi-tenant membership and authorized tenant selection.

## 28. `ELMOS-SEC-005`

**Skill:** `elmos-identity-tenant-security`  
**Group:** OIDC and sessions  
**Priority/Phase:** `P0` / `G1`

Check account disablement, membership revocation, and token/session revocation.

Acceptance hint: Implement and verify: Check account disablement, membership revocation, and token/session revocation.

## 29. `ELMOS-SEC-006`

**Skill:** `elmos-identity-tenant-security`  
**Group:** OIDC and sessions  
**Priority/Phase:** `P0` / `G1`

Proxy browser calls through a secure session layer and remove fixed tenant injection.

Acceptance hint: Implement and verify: Proxy browser calls through a secure session layer and remove fixed tenant injection.

## 30. `ELMOS-SEC-007`

**Skill:** `elmos-identity-tenant-security`  
**Group:** OIDC and sessions  
**Priority/Phase:** `P0` / `G1`

Implement a secure CLI login flow with short-lived credentials.

Acceptance hint: Implement and verify: Implement a secure CLI login flow with short-lived credentials.

## 31. `ELMOS-SEC-008`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Create tenant, user_account, membership, role, permission, role_permission, and resource_grant tables.

Acceptance hint: Implement and verify: Create tenant, user_account, membership, role, permission, role_permission, and resource_grant tables.

## 32. `ELMOS-SEC-009`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Define owner, tenant admin, project admin, migration engineer, reviewer, approver, runner operator, auditor, billing admin, and read-only roles.

Acceptance hint: Implement and verify: Define owner, tenant admin, project admin, migration engineer, reviewer, approver, runner operator, auditor, billing admin, and read-only roles.

## 33. `ELMOS-SEC-010`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Authorize repository view, sync, clone, transform, and delivery separately.

Acceptance hint: Implement and verify: Authorize repository view, sync, clone, transform, and delivery separately.

## 34. `ELMOS-SEC-011`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Authorize project create, start, pause, resume, cancel, approve, archive, and delete separately.

Acceptance hint: Implement and verify: Authorize project create, start, pause, resume, cancel, approve, archive, and delete separately.

## 35. `ELMOS-SEC-012`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Authorize runner enrollment, drain, disable, certificate rotation, and logs separately.

Acceptance hint: Implement and verify: Authorize runner enrollment, drain, disable, certificate rotation, and logs separately.

## 36. `ELMOS-SEC-013`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Authorize artifact read, export, retention override, and delete separately.

Acceptance hint: Implement and verify: Authorize artifact read, export, retention override, and delete separately.

## 37. `ELMOS-SEC-014`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Authorize evidence, certification, policy exception, and approval separately.

Acceptance hint: Implement and verify: Authorize evidence, certification, policy exception, and approval separately.

## 38. `ELMOS-SEC-015`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Perform authorization in the service layer, not only UI.

Acceptance hint: Implement and verify: Perform authorization in the service layer, not only UI.

## 39. `ELMOS-SEC-016`

**Skill:** `elmos-identity-tenant-security`  
**Group:** RBAC and resource authorization  
**Priority/Phase:** `P0` / `G1`

Add IDOR and cross-resource tests.

Acceptance hint: Implement and verify: Add IDOR and cross-resource tests.

## 40. `ELMOS-SEC-017`

**Skill:** `elmos-identity-tenant-security`  
**Group:** PostgreSQL RLS  
**Priority/Phase:** `P0` / `G1`

Add tenant_id to every tenant-owned table and backfill safely.

Acceptance hint: Implement and verify: Add tenant_id to every tenant-owned table and backfill safely.
