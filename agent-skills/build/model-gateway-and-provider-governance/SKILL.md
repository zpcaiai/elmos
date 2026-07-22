---
name: model-gateway-and-provider-governance
description: Build or review the ELMOS model gateway for Codex, Claude, OpenHands, BYOK, private and offline models. Use for any model profile, routing, prompt assembly, retention, failover, evaluation, promotion, cost or kill-switch change.
---

# Model Gateway And Provider Governance

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Route all Agent calls through the gateway; provider adapters may not hold independent credentials or bypass policy.
- Apply classification, residency, provider, region, model version, tool, context-size, secret-scan and budget hard filters before scoring.
- Never fail over restricted or private-only code to a public provider; return HUMAN_REQUIRED when no compliant model remains.
- Persist hashes, structured results, usage and policy decisions by default, not full prompts or responses.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Block SECRET content and public routing for RESTRICTED_CODE.
- Prove BYOK credentials never enter prompt or workspace files.
- Re-evaluate new model versions and make the kill switch stop new calls.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

