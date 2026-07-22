---
name: customer-success-renewal-and-expansion
description: Build or review ELMOS customer health, success plans, value evidence, renewal timelines and expansion candidates. Use for adoption, renewal risk, repository/Runner/credit growth or next migration waves.
---

# Customer Success Renewal And Expansion

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Explain health with adoption, delivery, validation, value, support, Runner, credit, engagement and renewal context.
- Treat missing private-deployment usage as missing, never zero; low use after planned completion is not automatic churn risk.
- Require evidence and definitions for value claims such as time saved, CVEs removed or Recipe reuse.
- Generate renewal or expansion candidates only; never auto-upgrade, quote or pressure customers.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove completed success plans contextualize low usage.
- Separate customer-success permissions from sales and billing.
- Preserve milestone-based renewal actions at 180, 120, 90, 60 and 30 days.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

