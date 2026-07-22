---
name: tamper-evident-audit-and-compliance-export
description: Build or review ELMOS audit events, organization hash chains, signed checkpoints, WORM retention, SIEM export and offline verification. Use for identity, migration, Runner, Secret, model, billing, deletion, support or break-glass actions.
---

# Tamper Evident Audit And Compliance Export

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Separate audit from operational logs and capture actor, action, resource, decision, policy version, before/after hashes and correlation.
- Append only, hash canonical events with the previous hash, sign checkpoints and prevent writer updates/deletes.
- Fail closed for risk acceptance, break-glass, secret access, organization deletion, license changes and signing when audit is unavailable.
- Exclude secrets, full tokens, source code, full prompts and unnecessary personal data.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Detect mutation, gaps, duplicates and ordering errors offline.
- Resume exports from a cursor with batch hashes and delivery confirmation.
- Apply tenant access and legal hold to audit queries and retention.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

