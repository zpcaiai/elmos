# ADR-0030: Enterprise tenant and private execution control

- Status: Accepted
- Date: 2026-07-21

## Decision

ELMOS introduces a framework-free `enterprise-governance` domain and a separate `enterprise-control` boundary application. Every customer-owned object is scoped to a server-derived Organization. Batch 1–8 tables are upgraded in V9 with `organization_id`, transaction-scoped tenant context, forced PostgreSQL Row-Level Security, tenant indexes and a deny-on-missing-context policy. Application authorization and object ownership checks remain mandatory because [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html) is defense in depth, not the only authorization layer.

OIDC and SAML are replaceable external adapters. Protocol parsing, signature verification, Authorization Code flow and logout belong to maintained Spring Security integration rather than custom cryptography; the current boundary follows the official [OAuth/OIDC login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) and [SAML login](https://docs.spring.io/spring-security/reference/servlet/saml2/login/index.html) contracts. Until a tenant connection and credentials exist, both adapters remain `NOT_CONFIGURED`.

Private Runners use outbound control channels, independent identities, capability-bound short leases and source-upload policies. Kubernetes execution requires an enforcing NetworkPolicy implementation and the Restricted Pod Security Standard. Secret and model credentials remain external references with workload leases; Vault-style policies are deny by default. Audit and usage ledgers are append-only in both Java policy and PostgreSQL triggers.

## Consequences

Shared, dedicated, hybrid, private and air-gapped modes use one domain contract. Live SSO, mTLS Runner channels, Vault/KMS, external model providers, SIEM, signed release bundles, backups and disaster-recovery drills are external acceptance gates and cannot be inferred from unit tests. License expiry never prevents reading or exporting historical evidence.
