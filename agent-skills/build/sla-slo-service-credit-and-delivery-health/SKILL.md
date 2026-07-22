---
name: sla-slo-service-credit-and-delivery-health
description: Build or review ELMOS SLI, SLO, SLA measurements, exclusions, maintenance windows, breaches, service credits and delivery health. Use for platform, Runner channel, queue, support response, restore or private-deployment commitments.
---

# Sla Slo Service Credit And Delivery Health

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Store SLI measurement, SLO target and contractual SLA rule separately.
- Commit only to controllable service outcomes, not guaranteed completion of arbitrary legacy migrations.
- Apply exclusions only when contractually allowed and backed by evidence; do not broadly exclude all customer Runner problems.
- Generate capped service-credit adjustment requests, not formal accounting entries.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove missing exclusion evidence leaves the breach counted.
- Trace breach detection, validation, dispute, credit calculation and closure.
- Separate platform availability from project delivery-health indicators.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

