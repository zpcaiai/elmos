---
name: private-on-premises-and-air-gapped-deployment
description: Build or review ELMOS private, on-premises and air-gapped packaging, offline licenses, local registries, preflight, backup, restore, upgrade and DR. Use for any release bundle, disconnected installation, diagnostics or private deployment change.
---

# Private On Premises And Air Gapped Deployment

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Bundle pinned OCI images, charts, recipes, Maven dependencies, vulnerability data, SBOM, provenance, checksums, signatures, docs and upgrade tools.
- In AIR_GAPPED mode prohibit runtime Maven Central, GitHub, public models, telemetry, license servers, CDN, fonts and scripts.
- Verify media, signatures, checksums, malware scan and policy before import; support canary and rollback.
- License expiry must block new work after grace while preserving login, evidence read/export, backup and safe shutdown.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Prove core deterministic functions work without an LLM or public network.
- Restore tenant isolation, audit chains, evidence hashes, deletion tombstones and legal holds.
- Diagnostics must exclude secrets, source, full prompts and production data.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

