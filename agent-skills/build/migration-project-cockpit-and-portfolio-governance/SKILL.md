---
name: migration-project-cockpit-and-portfolio-governance
description: Build or review ELMOS portfolio and migration project cockpit facts, weighted progress, milestones, blockers, forecasts, risks, budgets and change requests. Use for executive, technical or delivery project views.
---

# Migration Project Cockpit And Portfolio Governance

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Use one fact model across executive and technical views from portfolio down to migration step.
- Compute progress from risk/work/critical-path weights, not raw task count.
- A failed critical gate forces RED and cannot be hidden by high percentage or manual override.
- Scope additions require a change request and recalculation of risk, effort, cost, milestones and entitlement.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove 85 percent progress plus a failed transaction gate is RED.
- Every blocker needs owner, dates, impact and next action.
- Keep forecast P50/P80 and customer wait separate from technical wait.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

