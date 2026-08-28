# Implementation Guide — Agent Protocol Version Negotiation Governor

## Purpose

Govern exact MCP, A2A, ACP and UI protocol versions, extensions, downgrade, deprecation and evidence invalidation.

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

1. discover peer versions and extensions
2. select compatible profile with no silent downgrade
3. record unsupported/deprecated capabilities
4. test mixed-version rollout and fallback
5. invalidate evidence after protocol change

## Native acceptance corpus

- `ELMOS_AGENT_PROTOCOL_VERSION_NEGOTIATION_GOVERNOR-01` — native scenario: discover peer versions and extensions
- `ELMOS_AGENT_PROTOCOL_VERSION_NEGOTIATION_GOVERNOR-02` — native scenario: select compatible profile with no silent downgrade
- `ELMOS_AGENT_PROTOCOL_VERSION_NEGOTIATION_GOVERNOR-03` — native scenario: record unsupported/deprecated capabilities
- `ELMOS_AGENT_PROTOCOL_VERSION_NEGOTIATION_GOVERNOR-04` — native scenario: test mixed-version rollout and fallback
- `ELMOS_AGENT_PROTOCOL_VERSION_NEGOTIATION_GOVERNOR-05` — native scenario: invalidate evidence after protocol change

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
