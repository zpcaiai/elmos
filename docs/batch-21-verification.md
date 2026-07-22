# Batch 21 verification

## Repository-complete scope

- Independent Java 21 `ELMOS_ENTERPRISE_SUITE` Worker with capabilities, scan, plan, leased execute-step, validate, tenant-scoped job query, and cancellation contracts.
- Eighteen Runtime Skills for the engine contract, suite estate, process and capability graph, customization/clean-core classification, enterprise objects and master data, target planning, SAP, Oracle, Dynamics, Salesforce, MDM, data migration/archive/reconciliation, integration decoupling, workflow/report modernization, identity/SOD, semantic equivalence, ALM/cutover/decommission, and unified evidence.
- Nine fail-closed Adapter declarations, eight Draft 2020-12 schemas, ten fixtures including the requested matrix and 30 acceptance scenarios, OpenAPI 3.1, three policy manifests, six deterministic engine artifacts, and four isolated Runner policies.
- Shared Engine API, routing, portfolio dependency types, control-plane read/evaluate API, and independent Cutover and Decommission decisions. Cutover does not prematurely require post-cutover zero-usage, archive, credential, license, or legal-hold evidence; Decommission does.
- Flyway V23 covers all 63 requested suite objects by creating 62 strong-RLS projections and extending Batch 13's existing forced-RLS `business_capabilities` authority. V23 is physical migration 23 because the pre-existing product-ecosystem migration owns V22; existing shared authorities are reused instead of duplicated.

## Evidence boundary

Repository evidence proves deterministic acceptance policy, contract/fixture integrity, tenant and idempotency boundaries, default read-only discovery, lease/environment-scope enforcement, denial of production suite operations, business-process and data-migration authorization checks, and separation between Workers and Cutover authority. It does not prove a customer suite estate was scanned, transformed, reconciled, cut over, or retired.

The following remain `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, `BLOCKED`, external, or require 现场 evidence:

- Customer SAP, Oracle EBS/Fusion, Dynamics/Dataverse/Power Platform, Salesforce, Process Mining, MDM and archive adapters;
- Customer configuration exports, custom code, extension usage, process variants, master data, open transactions, financial balances, inventory, roles/SOD, reports, integrations, batch schedules, historical obligations, owners and approvals;
- Licensed product sandboxes, synthetic companies and users, production-like volumes, real migration loads, financial and inventory reconciliation, business-process semantic equivalence, parallel run, production cutover, master-data authority switch, stability hold, archive access and decommission evidence.

No successful metadata parse proves business-process equivalence. No record-count match proves financial balance, inventory valuation, referential completeness or Golden Record correctness. No unit test or Worker response authorizes production deployment, Cutover, data-authority transfer or retirement.

## Verification commands

```bash
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py agent-skills/runtime/<batch-21-skill>
JAVA_HOME=/opt/homebrew/opt/openjdk@21 /opt/homebrew/bin/mvn -B clean verify
PATH=/opt/homebrew/bin:$PATH dotnet test engines/dotnet-engine/Elmos.Dotnet.slnx
/opt/homebrew/bin/uv --directory engines/python-engine run --locked pytest
/opt/homebrew/bin/uv --directory engines/python-engine run --locked ruff check src tests
/opt/homebrew/bin/uv --directory engines/python-engine run --locked mypy src
PATH=/Users/stephen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin /opt/homebrew/bin/pnpm --dir engines/frontend-client-engine check
PATH=/Users/stephen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin /opt/homebrew/bin/pnpm --dir apps/web-console check
/Applications/Docker.app/Contents/Resources/bin/docker compose -f deploy/compose/docker-compose.yml config --quiet
```

Direct PostgreSQL 17 validation must run V1–V23 against a fresh database and verify the 62 V23-created tables, the extended `business_capabilities` authority, forced RLS policies, identity indexes, append-only triggers, and effective cross-tenant isolation. HTTP validation must start the packaged Worker on an isolated port and confirm fail-closed behavior without approved adapters, leases, scopes, sandbox/data authorization, or independent production approval.

## Verification status

Repository implementation and the closing verification run completed on 2026-07-21:

- Maven clean verification: 53 reactor projects, 118 Surefire reports, 759 tests, 0 failures, 0 errors, and 1 expected skip for the Docker-conditioned Flyway test. The Enterprise Suite engine contributes 42 passing tests, including all 30 acceptance scenarios.
- Direct PostgreSQL 17 fresh-database migration: V1–V23 completed. V1–V22 contained 1,286 public tables; V23 added 62, extended Batch 13's `business_capabilities` with all 14 suite projection fields, and finished with 1,348 public tables. All 62 new tables have forced RLS and one tenant policy; the reused authority remains forced-RLS. Seven identity indexes and 15 append-only triggers exist. A tenant-A session saw one tenant-A row, a tenant-B session saw none, and a tenant-A write for tenant B was rejected by RLS. The fresh migration caught and drove the removal of the initial duplicate `business_capabilities` creation.
- Packaged Worker HTTP: capabilities report nine adapters as `NOT_CONFIGURED`, control-plane execution `false`, and production mutation `DENY`. Discovery returned `SUITE_RUNNER_REQUIRED` with `NOT_RUN`, zero evidence and no fabricated success. Missing lease, sandbox authorization, data-migration authorization and independent production approval returned their dedicated errors; a production transport request returned `POLICY_BLOCKED`; an otherwise approved request without an adapter returned `SUITE_RUNNER_REQUIRED`. No production state, financial difference or SOD acceptance changed.
- Cross-engine regression: .NET 12/12 tests; Python 31/31 tests plus clean Ruff and MyPy checks; Frontend Client engine 34/34 tests.
- Skills and static artifacts: all 18 Batch 21 Skills passed `quick_validate.py`; the repository contains 236 Runtime and 35 Build Skills. All 31 Batch 21 JSON artifacts and both YAML files parse successfully with no Batch 21 TODO, placeholder or simulated-success marker.
- Delivery surface: the Next.js 16.2.10 production build and Docker Compose configuration validation passed, and Compose exposes `enterprise-suite-engine-worker`. Executable JAR packaging and the isolated local HTTP run passed; the process was stopped after validation. Container image construction was not executed because the configured Docker/OrbStack daemon was unavailable, so no container-runtime evidence is claimed.

Real customer enterprise-suite execution remains external and is not represented as completed.
