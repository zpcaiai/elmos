---
name: recipe-asset-marketplace-and-commercial-licensing
description: Build or review ELMOS marketplace assets, listings, certification, licensing, pricing, installation, pinning, recall and partner usage. Use for Recipes, Repair Skills, validation profiles, templates, images or playbooks offered beyond one project.
---

# Recipe Asset Marketplace And Commercial Licensing

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Keep customer assets PRIVATE by default; publication requires explicit IP, anonymization and customer approval.
- Certify only with clear license, SBOM, signature, tests, idempotence, security, canary, docs and maintainer.
- Installation must pass entitlement, license, signature, compatibility and sandbox gates; approved plans freeze versions.
- Recall blocks new install/execution but preserves historical run evidence.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Reject accidental publication of customer-specific assets.
- Prove BLOCKED/REVOKED assets cannot be selected by new plans.
- Bind reviews to real usage without exposing customer technology.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

