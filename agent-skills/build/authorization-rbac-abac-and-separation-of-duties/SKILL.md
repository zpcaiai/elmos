---
name: authorization-rbac-abac-and-separation-of-duties
description: Build or review ELMOS object-level RBAC, ABAC, separation of duties, temporary privilege and break-glass authorization. Use for every protected API, background job, approval, risk acceptance, execution, billing, runner or support action.
---

# Authorization Rbac Abac And Separation Of Duties

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Model permissions as resource:action and check both role permission and concrete resource ownership.
- Apply ABAC attributes for risk, classification, deployment, runner, assurance, approvals, region and contract.
- Default to DENY and return versioned, explainable ALLOW, DENY, conditional, approval or step-up decisions.
- Separate plan author, executor, reviewer, risk approver and final acceptor for critical flows.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove billing and audit roles cannot read source or execute migrations.
- Expire temporary privileges automatically and reauthorize after policy changes.
- Apply the same authorization service to API, UI and service identities.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

