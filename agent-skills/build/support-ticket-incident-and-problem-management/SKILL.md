---
name: support-ticket-incident-and-problem-management
description: Build or review ELMOS support tickets, severity, incidents, timelines, problem records, known errors, resolutions and controlled support access. Use for customer questions, migration failures, Runner/model/billing/security issues or incidents.
---

# Support Ticket Incident And Problem Management

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Compute severity from impact and urgency; evidence integrity, suspected exposure and multi-customer outages are SEV1.
- Link tickets to organization, repository, run, step, runner, invocation, evidence, subscription and SLA.
- Ticket existence never grants source access; require scoped, time-bound customer or contract authorization.
- Agents may suggest knowledge but cannot close SEV1, promise compensation, access source or publish postmortems.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove SEV1 creates an incident commander and update cadence.
- Cluster repeated fingerprints into Problem Records and Known Errors.
- Require resolution evidence and SLA outcome before closure.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

