# Batch 17 verification

## Repository-complete scope

- Independent Java 21 `ELMOS_SECURITY_COMPLIANCE` worker with shared `/engine/v1` jobs and `/engine/v1/authorize`.
- Seventeen validated Runtime Skills covering estate, identity, secrets/crypto, SSDF, supply chain, static/dynamic/runtime testing, vulnerability risk, cloud, data protection, threats, detection/response, control mapping, OSCAL, continuous authorization, and ELMOS delivery.
- Eighteen fail-closed Tool Adapter declarations, five security profiles, nine Draft 2020-12 schemas and fixtures, and 30 executable acceptance scenarios.
- Shared router/portfolio and control-plane policy integration without loading scanner SDKs or executing customer targets.
- Flyway V17 creates 94 strong-RLS security projections and extends six existing Identity, Secret, Risk, and Authorization authorities rather than duplicating them.

## Evidence boundary

The repository tests prove deterministic policy, schema/fixture integrity, tenant/idempotency boundaries, explicit active-test authorization, internal authorization expiry, adapter fail-closed behavior, and database migration structure. They do not prove a customer estate is secure, compliant, certified, authorized by a regulator, or ready for production.

The following remain `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, `COVERAGE_INSUFFICIENT`, or `BLOCKED` until authorized external evidence exists:

- real SAST, SCA, secret, IaC, container, DAST, API, cloud, Kubernetes, runtime, DLP, SIEM, SBOM, provenance, VEX, or OSCAL tools;
- customer IdP/PAM/workload identity, Vault/KMS/PKI, repositories, registries, cloud accounts, clusters, workloads, databases, data flows, prompts, telemetry, incidents, or control catalogs;
- active testing authorization and safe target environments;
- human threat/risk review, exception approval, control assessment, audit opinion, ISO/SOC/regulatory certification, and formal ATO.

An adapter reporting no findings is not a security pass when coverage, parsing, target reachability, tool health, or evidence freshness is insufficient. Internal `AUTHORIZED` is time-bound and never represents external certification.

## Verification commands

```bash
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py agent-skills/runtime/<batch-17-skill>
JAVA_HOME=/opt/homebrew/opt/openjdk@21 /opt/homebrew/bin/mvn -B verify
PATH=/Users/stephen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin /opt/homebrew/bin/pnpm --dir apps/web-console check
```

Direct PostgreSQL 17 migration validation should run V1–V17 against a fresh database and verify table, RLS policy, and append-only trigger counts. HTTP validation should start the packaged worker on an isolated port, confirm capabilities, observe a fail-closed scan, block an unapproved active test, and verify that internal authorization never sets `externalCertificationGranted=true`.

## Verified on 2026-07-21

- `mvn -B clean verify`: 46 modules, 85 reports, 468 tests, 0 failures, 0 errors. The Docker-dependent Flyway Testcontainers case was the single skip because the local Docker daemon was unavailable.
- Direct PostgreSQL 17.5 execution of V1–V17 closed that skip's evidence gap: 943 public tables, 942 tenant-isolation policies, 220 append-only triggers, 94 V17-created tables, all 24 sampled core tables, and the external-certification guard were present.
- Packaged HTTP worker on an isolated local port: 18 adapters reported `NOT_CONFIGURED`; scan returned `FAILED` / `SECURITY_TOOL_UNAVAILABLE` / `NOT_RUN` with zero evidence; unapproved DAST returned `SECURITY_TEST_AUTHORIZATION_REQUIRED`; internal authorization returned `AUTHORIZED`, `internalDecisionOnly=true`, `externalCertificationGranted=false`.
- Skill validation: all 17 Batch 17 Skills passed and the Runtime Skill inventory is 165.
- Cross-engine regression: .NET 12/12, Python 31/31 plus Ruff and mypy, Frontend Client 34/34, and the Next.js console production build passed.
- JSON parsing and `docker compose config --quiet` passed. Docker image build, real adapters, customer targets, and external authorities remain outside repository evidence and retain the statuses listed above.
