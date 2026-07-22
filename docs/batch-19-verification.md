# Batch 19 verification

## Repository-complete scope

- Independent Java 21 `ELMOS_MAINFRAME` worker with capabilities, discover, analyze, plan, transform, leased execute, validate, rule approval, tenant-scoped job query, and cancellation contracts.
- Eighteen Runtime Skills covering z/OS runners, estate/source/runtime correlation, COBOL/copybook/JCL/CICS/IMS/Db2/VSAM semantics, rules and domain slices, target planning, APIs, refactoring, batch, 3270 journeys, data authority, DevSecOps, semantic validation, parallel run, cutover, decommission, and unified evidence.
- Ten fail-closed adapter declarations, six runner classes, eight Draft 2020-12 schemas and fixtures, OpenAPI 3.1, the requested fixture matrix, three distributed sandbox policies, and 30 executable acceptance scenarios.
- Shared Engine API, language routing, portfolio dependency types, control-plane read/evaluate API, and separate independent cutover and decommission decisions without z/OS execution or gate mutation. Cutover does not incorrectly require post-cutover zero-usage or credential-revocation evidence; decommission does.
- Flyway V19 creates all 82 requested strong-RLS mainframe projections, adds stable source/copybook/load-module identities and domain-specific constraints, and protects run, version, transformation, comparison, cutover, and retirement evidence as append-only.

## Evidence boundary

Repository evidence proves deterministic policy, contract/fixture integrity, tenant and idempotency boundaries, default read-only discovery, lease/dataset-scope enforcement, denial of arbitrary JCL and unapproved production writes, candidate-only AI/rules, and separation between workers and cutover authority. It does not prove a customer mainframe was scanned, built, tested, transformed, cut over, or retired.

The following remain `NOT_CONFIGURED`, `NOT_RUN`, `INCONCLUSIVE`, or `BLOCKED`:

- z/OSMF, SSH/USS, SCM, application-discovery, CICS, IMS, Db2, CDC, scheduler, watsonx, Test Accelerator for Z, RACF/SAF, and promotion adapters;
- customer source, copy libraries, build listings, binder maps, load modules, runtime/SMF evidence, JCL, scheduler calendars, CICS/IMS resources, Db2/VSAM/file data, 3270 sessions, owners, and business approvals;
- compiler, precompiler, binder, licensed test, z/OS CPU/capacity, production-like data, live semantic comparison, online shadow, batch parallel, traffic/data-authority cutover, rollback, stability hold, and decommission evidence.

No active load module may be transformed or retired without source/build correlation. No rule candidate is authoritative without a business owner. No green compile or reduced test subset proves semantic equivalence. No online cutover authorizes a batch or writer cutover. No zero internal traffic proves retirement while external consumers or RACF credentials remain.

## Verification commands

```bash
python3 /Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py agent-skills/runtime/<batch-19-skill>
JAVA_HOME=/opt/homebrew/opt/openjdk@21 /opt/homebrew/bin/mvn -B clean verify
PATH=/Users/stephen/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:/opt/homebrew/bin:/usr/bin:/bin /opt/homebrew/bin/pnpm --dir apps/web-console check
/usr/local/bin/docker compose -f deploy/compose/docker-compose.yml config --quiet
```

Direct PostgreSQL 17 validation must run V1–V19 against a fresh database and verify the 82 V19 tables, forced RLS policies, identity indexes, and append-only triggers. HTTP validation must start the packaged worker on an isolated port and confirm `NOT_RUN` behavior without approved adapters, leases, dataset scopes, or independent production approval.

## Verified on 2026-07-21

- Java 21 Maven verification passed across all 50 reactor projects. The final run produced 102 Surefire XML reports covering 635 tests, with 0 failures, 0 errors, and one Docker-dependent Flyway Testcontainers case skipped. The Mainframe Engine contributes 41 tests, including all 30 Batch 19 acceptance scenarios.
- Direct PostgreSQL 17 execution of V1–V20 on a fresh temporary instance closed the skipped migration evidence path for Batch 19: all 82 requested V19 tables exist, all 82 force RLS, all 82 have `tenant_isolation`, the three source/copybook/load-module identity indexes exist, and all 15 V19 append-only trigger definitions were installed. The temporary instance was stopped and moved to Trash.
- The packaged worker on isolated port 18093 reported `ELMOS_MAINFRAME` 1.0.0, `controlPlaneExecution=false`, production writes `DENY`, and every adapter `NOT_CONFIGURED`. Discovery returned `FAILED / MAINFRAME_RUNNER_REQUIRED / NOT_RUN` with zero evidence; missing leases returned `MAINFRAME_LEASE_REQUIRED`; approved scopes without an adapter still returned `MAINFRAME_RUNNER_REQUIRED` and `customerCodeExecuted=false`; an unapproved production write returned `MAINFRAME_PRODUCTION_APPROVAL_REQUIRED` and `productionStateChanged=false`; an inferred rule without a business owner remained non-authoritative.
- All 18 Batch 19 Skills passed `quick_validate.py`; effective inventories are 200 Runtime Skills and 35 Build Skills. All eight schemas, fixtures, policies, acceptance data, and three sandbox-policy JSON files parse successfully. Docker Compose configuration and the Next.js 16.2.10 production build passed.
- Cross-engine regression passed: .NET 12/12, Python 31/31 plus Ruff and mypy, and Frontend Client 34/34.
- Docker image construction, real mainframe adapters, customer assets, z/OS execution, live semantic comparison, parallel run, production cutover, RACF change, and decommission were not run and retain the external statuses above. The local Docker daemon was unavailable.
