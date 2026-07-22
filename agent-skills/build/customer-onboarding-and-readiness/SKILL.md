---
name: customer-onboarding-and-readiness
description: Build or review ELMOS customer onboarding templates, tasks, environment inventory, network probes, security questionnaire, readiness and pilot gates. Use before any enterprise customer starts a formal migration project.
---

# Customer Onboarding And Readiness

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Select templates by SaaS, hybrid, private or air-gapped deployment.
- Give each task customer and ELMOS owners, evidence, dependencies, due dates and a blocking flag.
- Assess identity, SCM, Runner, secrets, models, dependencies, build, test, security, data, governance, support and pilot readiness.
- Do not replace formal customer security review or upload credentials with readiness probes.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Block formal migration when any required dimension is not ready.
- Require representative, reversible pilot selection rather than a trivial demo.
- Expose blockers, owners and next actions to the project cockpit.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

