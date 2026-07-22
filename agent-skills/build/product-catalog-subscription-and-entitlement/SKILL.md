---
name: product-catalog-subscription-and-entitlement
description: Build or review ELMOS product catalog, subscriptions, private licenses, trials, allowances and runtime entitlements. Use whenever a feature, edition, add-on, plan limit, license or paid capability is introduced or checked.
---

# Product Catalog Subscription And Entitlement

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Separate prices from runtime entitlements and use stable feature keys rather than plan-name conditionals.
- Apply security and contract restrictions before license, subscription, trial and product defaults.
- Return versioned ALLOW or explicit denial/upgrade/add-on decisions with source entitlement IDs and remaining allowance.
- Cache briefly, invalidate on change and recheck high-risk operations; failures never default open.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove Assessment entitlement does not grant Migration.
- Make concurrent allowance consumption safe and manual grants expire.
- License or subscription expiry must preserve historical report/evidence access.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

