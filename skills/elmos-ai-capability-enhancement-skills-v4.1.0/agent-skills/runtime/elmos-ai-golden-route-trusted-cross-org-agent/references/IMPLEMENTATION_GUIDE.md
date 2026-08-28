# Implementation Guide — Golden Route: Trusted Cross-Organization Agent

## Purpose

Certify signed A2A discovery, workload identity, delegated authority and auditable cross-organization task execution.

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

1. Signed Agent Card exchange
2. Trust registry and version negotiation
3. Workload attestation
4. Attenuated downstream delegation
5. Revocation and incident drill

## Native acceptance corpus

- `ELMOS_AI_GOLDEN_ROUTE_TRUSTED_CROSS_ORG_AGENT-01` — two trust domains
- `ELMOS_AI_GOLDEN_ROUTE_TRUSTED_CROSS_ORG_AGENT-02` — tampered card
- `ELMOS_AI_GOLDEN_ROUTE_TRUSTED_CROSS_ORG_AGENT-03` — unattested workload
- `ELMOS_AI_GOLDEN_ROUTE_TRUSTED_CROSS_ORG_AGENT-04` — delegation boundary
- `ELMOS_AI_GOLDEN_ROUTE_TRUSTED_CROSS_ORG_AGENT-05` — tenant isolation
- `ELMOS_AI_GOLDEN_ROUTE_TRUSTED_CROSS_ORG_AGENT-06` — revocation during run

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
