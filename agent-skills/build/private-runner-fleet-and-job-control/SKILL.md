---
name: private-runner-fleet-and-job-control
description: Build or review ELMOS private runner enrollment, mTLS identity, capability routing, job leases, heartbeats, source-upload policy, draining, quarantine and upgrade. Use whenever code must remain in a customer network or a runner claims execution work.
---

# Private Runner Fleet And Job Control

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Use outbound-only control channels, one runner certificate per node and short-lived job tokens; never provide control-plane shell access.
- Match organization, pool, region, classification and every hard capability before leasing a job.
- Make Claim, Lease, Heartbeat and Completion idempotent by job, attempt, manifest hash and idempotency key.
- For Kubernetes use Restricted pod security, default-deny networking, no privilege/hostPath and cleanup of pods and volumes.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Reject unregistered, cross-tenant, mismatched and expired-lease work.
- Reject late results from old attempts and revoke secrets on loss or quarantine.
- Prove NO_SOURCE_UPLOAD permits only hashes, findings and approved redacted evidence.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

