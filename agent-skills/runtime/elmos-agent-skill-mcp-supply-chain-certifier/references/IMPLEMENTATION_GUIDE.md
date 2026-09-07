# Implementation Guide — Agent Skill and MCP Supply Chain Certifier

## Purpose

Certify Skills, plugins and MCP servers with publisher identity, signatures, SBOM/AIBOM, reproducible builds, permission diffs and static/dynamic behavior evidence.

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

1. Publisher and package identity
2. Dependency and resource inventory
3. Reproducible build and provenance
4. Install/update permission diff
5. Static and sandboxed dynamic behavior analysis

## Native acceptance corpus

- `ELMOS_AGENT_SKILL_MCP_SUPPLY_CHAIN_CERTIFIER-01` — signed trusted package
- `ELMOS_AGENT_SKILL_MCP_SUPPLY_CHAIN_CERTIFIER-02` — unsigned package block
- `ELMOS_AGENT_SKILL_MCP_SUPPLY_CHAIN_CERTIFIER-03` — typosquat fixture
- `ELMOS_AGENT_SKILL_MCP_SUPPLY_CHAIN_CERTIFIER-04` — hidden script detection
- `ELMOS_AGENT_SKILL_MCP_SUPPLY_CHAIN_CERTIFIER-05` — permission expansion block
- `ELMOS_AGENT_SKILL_MCP_SUPPLY_CHAIN_CERTIFIER-06` — reproducible build

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
