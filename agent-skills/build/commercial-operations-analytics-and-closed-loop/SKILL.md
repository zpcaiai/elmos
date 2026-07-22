---
name: commercial-operations-analytics-and-closed-loop
description: Build or review ELMOS commercial analytics across acquisition, activation, delivery, economics, retention and asset leverage. Use for unit economics, cost anomalies, productization candidates, renewal analysis or operational alerts.
---

# Commercial Operations Analytics And Closed Loop

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Version every metric definition and record source, window, currency, coverage and missing-data status.
- Do not treat missing private-deployment usage as zero and do not use this analytics layer as financial revenue recognition.
- Restrict revenue and engineer-cost data independently from source code and technical quality data.
- Turn repeated evidence-backed work into reviewable Recipe, connector, validation, feature or playbook candidates.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove 300 percent cost shifts create alerts without changing customer prices.
- Require multiple organizations and evidence for productization candidates.
- Trace every commercial decision back to delivery and usage facts.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

