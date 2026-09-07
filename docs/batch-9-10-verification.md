# Batch 9–10 verification and external gates

## Local evidence (2026-07-21)

- `mvn -B verify`: 38 reactor modules succeeded; 167 tests, 0 failures, 0 errors, 1 skipped. The skipped test is the Testcontainers Flyway test because the Docker API was unavailable.
- Direct PostgreSQL 17 migration verification on a temporary local instance: V1–V10 applied in version order; 391 public business tables, 390 RLS policies, and 391 `organization_id` columns. A non-owner role saw only its own organization's row and an append-only audit update was rejected.
- `pnpm --dir apps/web-console check`: TypeScript and the Next.js production build succeeded.
- The packaged `enterprise-control` and `commercial-api` applications started on Java 21; both actuator health endpoints returned `UP`. Their capability endpoints reported local policy services as `AVAILABLE` while OIDC, SAML, private Runner, external secrets/models, CRM and payment remained `NOT_CONFIGURED`, and formal accounting remained `OUT_OF_SCOPE`.
- JSON/YAML syntax checks passed for 85 JSON artifacts and 16 YAML documents. All 35 Build Skills passed frontmatter/name/directory validation; the B016–B035 additions also passed three adversarial total-skill evaluations with 12/12 assertions.
- `elmosctl` returned `BLOCKED` without both approval flags, `ACCEPTED_FOR_EXTERNAL_EXECUTION` with both flags, and `NOT_RUN` for verification without a release bundle/installation target.

The direct database instance was temporary and is no longer running. Docker images and the containerized Flyway path remain unverified in this environment.

## Repository-verifiable scope

| Batch | Implemented locally | Binding boundary |
|---|---|---|
| 9 | Server-derived tenant context, RBAC/ABAC/SoD, federated identity policy, Runner/Secret leases, model hard filters, concurrent usage ledger, tamper-evident audit, retention/legal hold, offline bundle and license policy | External IdP, mTLS Runner, Vault/KMS, model provider, SIEM, signed release media, backup/restore and DR require customer infrastructure |
| 10 | Entitlements, idempotent partial order fulfillment, onboarding readiness, weighted project health, SLA decisions, support triage, marketplace/knowledge governance, customer health and commercial analytics | CRM, contracts, payment, tax, formal invoicing/accounting, notifications and marketplace settlement remain external Ports |

## Required live acceptance sequence

1. Configure two real organizations and a non-owner application database role. Prove API, repository, cache, search, event, object-storage URL and PostgreSQL RLS isolation in both directions, including pooled-connection reuse.
2. Configure one OIDC and one SAML test IdP. Exercise issuer, audience, nonce, signed assertion, group removal, local/provider logout, step-up and disabled-user session revocation.
3. Enroll a private Runner with mTLS through an outbound-only channel. Prove certificate uniqueness, capability routing, lost lease recovery, stale-attempt rejection, drain, quarantine and source-upload enforcement.
4. Configure an approved Secret Provider and prove dynamic credential issue/revoke, purpose separation, rotation, signing-service isolation and audit redaction.
5. Configure a private model plus one permitted external model. Prove RESTRICTED_CODE cannot fail over publicly, BYOK remains tenant scoped, retention is honored and a kill switch stops new calls.
6. Run concurrent usage reservations against PostgreSQL, reconcile provider usage to versioned cost snapshots, and test refunds and reversal entries.
7. Export and independently verify an audit chain and signed checkpoint; interrupt the export and resume from its cursor.
8. Exercise retention, an active Legal Hold, full deletion, backup restore and deletion-tombstone replay without exposing deleted content in evidence.
9. Import a signed offline release bundle into a disconnected test environment. Prove no public DNS/network dependency, no external page assets, local license verification, no-Agent deterministic operation, backup/restore and failed-upgrade rollback.
10. Replay duplicated order events, partial fulfillment, entitlement races, blocked onboarding, critical project gates, evidenced SLA exclusions, SEV1 response, private asset publication denial and asset recall.
11. Connect external contract/payment/invoice test doubles and reconcile ELMOS fulfillment requests without treating them as formal accounting entries.

## Fail-closed meaning

`NOT_CONFIGURED` means no tenant-scoped external adapter exists. `NOT_RUN` means a live action did not execute. `BLOCKED` means policy rejected it. `MISSING` and `INCONCLUSIVE` remain non-passing. None may be rendered as an active SSO connection, Runner, payment, invoice, financial result, offline installation or completed customer delivery.
