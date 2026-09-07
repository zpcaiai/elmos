# Implementation Guide — MCP Enterprise Authorization Controller

## Purpose

Generate and verify OAuth/OIDC, client registration, delegated consent, audience restriction, token exchange, revocation and enterprise-managed MCP authorization.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. OAuth/OIDC discovery and exact issuer binding
2. Dynamic or managed client registration
3. User delegation and resource indicators
4. Scoped consent and token exchange
5. Revocation, expiry and downstream audience enforcement

## Native acceptance corpus

- `ELMOS_MCP_ENTERPRISE_AUTHORIZATION_CONTROLLER-01` — valid delegated access
- `ELMOS_MCP_ENTERPRISE_AUTHORIZATION_CONTROLLER-02` — missing consent denial
- `ELMOS_MCP_ENTERPRISE_AUTHORIZATION_CONTROLLER-03` — wrong audience denial
- `ELMOS_MCP_ENTERPRISE_AUTHORIZATION_CONTROLLER-04` — expired/revoked token
- `ELMOS_MCP_ENTERPRISE_AUTHORIZATION_CONTROLLER-05` — scope escalation denial
- `ELMOS_MCP_ENTERPRISE_AUTHORIZATION_CONTROLLER-06` — issuer mix-up test

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
