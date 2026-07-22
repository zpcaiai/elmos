# Batch 18 verification

## Repository-complete scope

- Independent Java 21 `ELMOS_TEST_QUALITY` worker with `/engine/v1/capabilities`, discover, plan, generate, execute, evaluate, job, cancel, and governed AI-candidate promotion contracts.
- Seventeen validated Runtime Skills covering estate discovery, risk graphs, portfolio planning, characterization, contracts, property/model/fuzz, mutation, test data, virtualization/environments, journeys/nonfunctional validation, AI candidates, flaky governance, impact selection, gates, continuous validation, and unified ELMOS evidence.
- Twelve fail-closed adapter declarations, six runner classes, eight Draft 2020-12 schemas and fixtures, the requested fixture matrix, seven explicit sandbox policies, and 30 executable acceptance scenarios.
- Shared router/portfolio and control-plane policy integration without host test execution, production secrets, gate mutation, snapshot auto-approval, AI auto-promotion, or fabricated evidence.
- Flyway V18 creates 86 strong-RLS quality projections and extends the two V7 test identity authorities rather than duplicating them.

## Evidence boundary

Repository tests prove deterministic policy, schema/fixture integrity, stable model invariants, tenant/idempotency boundaries, adapter and lease fail-closed behavior, quality-gate separation of duties, and migration structure. They do not prove a customer system has adequate tests, is release-ready, or has run real browser/device/data/model/performance/mutation/production validation.

The following remain `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, or `BLOCKED` until authorized external evidence exists:

- real JUnit/.NET/pytest/JavaScript/Playwright/Pact/property/mutation/Testcontainers/WireMock/test-management adapters and licensed tools;
- customer source, builds, CI history, test-management/manual assets, requirements, risk owners, environments, production-like configuration, devices, data, models, dependencies, traces, incidents, and defect records;
- rootless digest-pinned runner images, environment/data/device leases, approved network egress, calibrated performance capacity, human golden-master/mutant/AI-test review, gate exception and business-risk acceptance;
- production synthetic/read-only/shadow/canary/post-deploy validation.

A green subset is not a pass when discovery counts disagree, tests are skipped/disabled, critical risk is uncovered, mutants survive, a critical journey is flaky, environment fidelity is insufficient, or evidence is stale.

## Verification commands

```bash
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py agent-skills/runtime/<batch-18-skill>
JAVA_HOME=/opt/homebrew/opt/openjdk@21 /opt/homebrew/bin/mvn -B clean verify
PATH=/Users/stephen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin /opt/homebrew/bin/pnpm --dir apps/web-console check
```

Direct PostgreSQL 17 validation should run V1–V18 against a fresh database and verify table, forced-RLS policy, and append-only trigger counts. HTTP validation should start the packaged worker on an isolated port, confirm capabilities, observe fail-closed discovery/execution/evaluation, and verify AI promotion fails without human review.

## Verified on 2026-07-21

- Java 21 Maven reactor verification passed across 48 projects. A final post-change run produced 92 Surefire XML reports covering 518 tests, with 0 failures, 0 errors, and the single Docker-dependent Flyway Testcontainers case skipped because the local Docker daemon was unavailable. The Test Quality Engine contributes 43 tests, including all 30 acceptance scenarios.
- Direct PostgreSQL 17 execution of V1–V18 closed the skipped migration evidence path: 1029 public tables, 1028 tenant-isolation policies, 1028 forced-RLS tables, 288 append-only trigger event registrations, all 88 requested Batch 18 objects, exactly 86 V18-created tables, and all nine stable Test Identity dimension columns were present. V18 adds 34 append-only trigger definitions.
- Packaged HTTP worker on isolated port 18092 reported `ELMOS_TEST_QUALITY` 1.0.0, adapters `NOT_CONFIGURED`, and `workerCanModifyGate=false`. Discovery returned `FAILED / TEST_QUALITY_RUNNER_REQUIRED / NOT_RUN` with zero evidence; missing leases returned `TEST_ENVIRONMENT_UNAVAILABLE`; approved leases without a runner still returned `TEST_QUALITY_RUNNER_REQUIRED` and `customerCodeExecuted=false`; AI promotion without a human returned `REVIEW_REQUIRED`; quality evaluation without independent evidence returned `INCONCLUSIVE`.
- All 17 Batch 18 Skills passed `quick_validate.py`; the effective Runtime Skill inventory is 182 and the Build Skill inventory remains 35. All eight schemas, fixtures, policies, and seven runner-policy JSON files parse successfully.
- Web console TypeScript and Next.js 16.2.10 production build passed; Docker Compose configuration parsed successfully. Cross-engine regression passed: .NET 12/12, Python 31/31 plus Ruff and mypy, and Frontend Client 34/34.
- Docker image construction, real framework/browser/device/data/model/performance/mutation runners, customer assets, external test-management systems, and production validation were not run and retain the external statuses above.
