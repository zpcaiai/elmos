# Identity, Tenant Isolation, Authorization, and Secrets

- Skill: `elmos-identity-tenant-security`
- Priority: `P0`
- Phase: `G1`
- Dependencies: `elmos-architecture-contract-governance`

## Objective

Make eLMOS safe to connect to customer private repositories by eliminating spoofable tenancy, shared credentials, superuser access, and secret leakage.

## Task groups

### OIDC and sessions

- [ ] `ELMOS-SEC-001` Add an OIDC resource server and validate issuer, audience, expiration, signature algorithm, nonce where applicable, and token type.
- [ ] `ELMOS-SEC-002` Resolve user only from validated token or server-side session.
- [ ] `ELMOS-SEC-003` Resolve active tenant from validated membership, never arbitrary headers.
- [ ] `ELMOS-SEC-004` Support multi-tenant membership and authorized tenant selection.
- [ ] `ELMOS-SEC-005` Check account disablement, membership revocation, and token/session revocation.
- [ ] `ELMOS-SEC-006` Proxy browser calls through a secure session layer and remove fixed tenant injection.
- [ ] `ELMOS-SEC-007` Implement a secure CLI login flow with short-lived credentials.

### RBAC and resource authorization

- [ ] `ELMOS-SEC-008` Create tenant, user_account, membership, role, permission, role_permission, and resource_grant tables.
- [ ] `ELMOS-SEC-009` Define owner, tenant admin, project admin, migration engineer, reviewer, approver, runner operator, auditor, billing admin, and read-only roles.
- [ ] `ELMOS-SEC-010` Authorize repository view, sync, clone, transform, and delivery separately.
- [ ] `ELMOS-SEC-011` Authorize project create, start, pause, resume, cancel, approve, archive, and delete separately.
- [ ] `ELMOS-SEC-012` Authorize runner enrollment, drain, disable, certificate rotation, and logs separately.
- [ ] `ELMOS-SEC-013` Authorize artifact read, export, retention override, and delete separately.
- [ ] `ELMOS-SEC-014` Authorize evidence, certification, policy exception, and approval separately.
- [ ] `ELMOS-SEC-015` Perform authorization in the service layer, not only UI.
- [ ] `ELMOS-SEC-016` Add IDOR and cross-resource tests.

### PostgreSQL RLS

- [ ] `ELMOS-SEC-017` Add tenant_id to every tenant-owned table and backfill safely.
- [ ] `ELMOS-SEC-018` Enable and force RLS on every tenant-owned table.
- [ ] `ELMOS-SEC-019` Create a migration role used only by schema tooling.
- [ ] `ELMOS-SEC-020` Create a non-owner, non-superuser runtime role without BYPASSRLS.
- [ ] `ELMOS-SEC-021` Set validated tenant context at transaction start and clear it before returning pooled connections.
- [ ] `ELMOS-SEC-022` Test that tenant variables cannot leak across pooled requests.
- [ ] `ELMOS-SEC-023` Fail startup if runtime user is owner, superuser, or BYPASSRLS.
- [ ] `ELMOS-SEC-024` Run cross-tenant attacks through application SQL and direct runtime-role SQL.

### Runner and service identity

- [ ] `ELMOS-SEC-025` Make enrollment tokens single-use, short-lived, scope-limited, and auditable.
- [ ] `ELMOS-SEC-026` Issue a unique runner identity after enrollment.
- [ ] `ELMOS-SEC-027` Authenticate runners with mTLS or equivalent workload identity.
- [ ] `ELMOS-SEC-028` Rotate runner certificates before expiry.
- [ ] `ELMOS-SEC-029` Support immediate revocation and deny-list propagation.
- [ ] `ELMOS-SEC-030` Authenticate internal services with mTLS and distinct audiences.
- [ ] `ELMOS-SEC-031` Ensure runner credentials cannot call user APIs.
- [ ] `ELMOS-SEC-032` Bind runner identity to tenant, region, capability, and permitted task scopes.

### Secret broker

- [ ] `ELMOS-SEC-033` Define SecretReference and remove plaintext credentials from task/workflow payloads.
- [ ] `ELMOS-SEC-034` Implement Vault, cloud secret manager, and development-only local adapters.
- [ ] `ELMOS-SEC-035` Lease GitHub, Maven, Gradle, npm, NuGet, PyPI, registry, database, and cloud credentials only at execution time.
- [ ] `ELMOS-SEC-036` Issue least-privilege credentials separately for clone, build, publish, and delivery.
- [ ] `ELMOS-SEC-037` Revoke secrets after completion, cancellation, timeout, or lease loss.
- [ ] `ELMOS-SEC-038` Redact secrets from logs, errors, traces, command lines, environment dumps, artifacts, and Evidence Packs.
- [ ] `ELMOS-SEC-039` Audit secret-reference access without values.
- [ ] `ELMOS-SEC-040` Fail non-development startup on empty/default/placeholder secrets.

### API and webhook hardening

- [ ] `ELMOS-SEC-041` Set request-body limits for JSON, upload, webhook, and log endpoints.
- [ ] `ELMOS-SEC-042` Apply user, tenant, IP, route, and expensive-operation rate limits.
- [ ] `ELMOS-SEC-043` Set request, upstream, idle, and streaming timeouts.
- [ ] `ELMOS-SEC-044` Configure CORS, Origin, CSRF, security headers, and cookie policy.
- [ ] `ELMOS-SEC-045` Move management endpoints to an internal port/network.
- [ ] `ELMOS-SEC-046` Validate webhook signature, delivery ID, timestamp, type, and replay window.
- [ ] `ELMOS-SEC-047` Encrypt or minimize raw webhook envelopes and apply retention.
- [ ] `ELMOS-SEC-048` Add privacy-safe structured request logs and correlation IDs.

## Validation

- [ ] Spoof user and tenant headers through every API.
- [ ] Run RLS attacks as the real runtime role, including pooled-connection leakage.
- [ ] Reuse an enrollment token and present a revoked certificate.
- [ ] Scan logs, traces, rows, artifacts, and evidence for seeded secret canaries.
- [ ] Run forged, stale, duplicate, and oversized webhook tests.

## Exit gate

- [ ] No caller selects a tenant without validated membership.
- [ ] Runtime SQL cannot bypass tenant isolation.
- [ ] Every runner/service has unique rotatable identity.
- [ ] No secret canary leaves the broker boundary.
- [ ] Security tests gate private-source access.
