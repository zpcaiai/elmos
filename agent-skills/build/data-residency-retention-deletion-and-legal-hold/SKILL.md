---
name: data-residency-retention-deletion-and-legal-hold
description: Build or review ELMOS data classification, pre-write region routing, inventory, retention, deletion, backup handling, crypto-shredding, tombstones and legal hold. Use whenever source, logs, prompts, evidence, audit, billing or backups are stored or removed.
---

# Data Residency Retention Deletion And Legal Hold

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Inventory every durable artifact before storage with organization, type, region, classification, retention and encryption context.
- Decide storage and processing region before writing; asynchronous relocation cannot repair an illegal initial write.
- Apply priority Legal Hold over regulatory minimum, contract, organization and product defaults.
- Delete primary, cache, indexes, object storage and modeled backups; replay deletion tombstones after restore.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Block deletion covered by an active legal hold.
- Do not call row deletion crypto-shredding without a dedicated destroyed key and known copies.
- Ensure deletion evidence contains counts and limitations but none of the deleted content.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

