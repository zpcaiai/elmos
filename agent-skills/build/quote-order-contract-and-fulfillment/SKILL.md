---
name: quote-order-contract-and-fulfillment
description: Build or review ELMOS quote versions, orders, contract references, approvals and idempotent fulfillment into subscriptions, entitlements, credits, Runner quotas, onboarding and work packages. Use for commercial promise-to-delivery changes.
---

# Quote Order Contract And Fulfillment

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Make submitted quote versions immutable; changes create a new version with approval evidence.
- Keep only contract references and approved summaries, not sensitive full contracts.
- Translate each accepted line into explicit rights and tasks; partial fulfillment remains visible.
- Treat payment, invoice, tax and formal contract systems as external ports.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Duplicate order events must not duplicate subscriptions, credits, licenses or onboarding.
- Prove partial fulfillment cannot become FULFILLED.
- Trace every entitlement and task to quote, order and contract reference.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

