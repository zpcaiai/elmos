---
name: quota-metering-credit-and-billing-ledger
description: Build or review ELMOS quota, usage metering, reservation, credit and billing ledgers. Use for seats, repositories, migrations, Runner concurrency, model tokens, compute, validation, storage, credits, price snapshots or refunds.
---

# Quota Metering Credit And Billing Ledger

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Keep quota, internal cost and customer charge as separate concepts and records.
- Use Estimate, Reserve, Consume, Commit or Release; hard-quota reservations must be concurrency safe.
- Make usage and ledger entries append-only and idempotent; correct with reversal entries, never mutation.
- Bind every charge to source, failure classification, price version, currency and cost snapshot; missing provider usage is not zero.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove duplicate events charge once and concurrent reservations never make balances negative.
- Prove platform failure refunds and unused reservation release behavior.
- Keep billing roles tenant-scoped and unable to read source.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

