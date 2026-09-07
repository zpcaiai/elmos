# Implementation Guide — Agent Registry and Resource Discovery Governor

## Purpose

Discover, verify, policy-filter, pin and continuously monitor agents, Skills, tools, MCP servers, models and related agentic resources.

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

1. Multi-registry discovery federation
2. Publisher and signature verification
3. Policy and residency filtering
4. Exact version and digest locking
5. Freshness, revocation and drift monitoring

## Native acceptance corpus

- `ELMOS_AGENT_REGISTRY_RESOURCE_DISCOVERY_GOVERNOR-01` — trusted discovery
- `ELMOS_AGENT_REGISTRY_RESOURCE_DISCOVERY_GOVERNOR-02` — untrusted publisher block
- `ELMOS_AGENT_REGISTRY_RESOURCE_DISCOVERY_GOVERNOR-03` — duplicate identity conflict
- `ELMOS_AGENT_REGISTRY_RESOURCE_DISCOVERY_GOVERNOR-04` — revoked resource removal
- `ELMOS_AGENT_REGISTRY_RESOURCE_DISCOVERY_GOVERNOR-05` — registry outage fallback
- `ELMOS_AGENT_REGISTRY_RESOURCE_DISCOVERY_GOVERNOR-06` — capability drift invalidation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
