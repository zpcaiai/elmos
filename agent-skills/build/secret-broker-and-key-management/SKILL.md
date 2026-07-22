---
name: secret-broker-and-key-management
description: Build or review ELMOS secret references, workload-scoped leases, provider adapters, key hierarchy, rotation, signing separation, redaction and access audit. Use whenever Git, Maven, model, database, registry, signing, backup or encryption credentials are needed.
---

# Secret Broker And Key Management

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Persist only Secret References; keep secret values in an approved provider and prohibit development providers in production.
- Bind each lease to organization, runner, job, migration step and one purpose; different purposes require different credentials.
- Prefer workload identity, dynamic credentials and tmpfs or short-lived descriptors over global environment variables.
- Separate signing keys from encryption keys and preserve verification across rotation.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove read credentials cannot write and model credentials never enter build processes.
- Revoke leases on completion, expiry and quarantine.
- Secret values must not enter logs, audit, events, evidence, reports or prompts.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

