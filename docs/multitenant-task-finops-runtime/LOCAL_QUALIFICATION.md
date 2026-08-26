# Local qualification and evidence boundary

## Current evidence state

The repository result register remains authoritative:

- implementation mapping is 63 `IMPLEMENTED`, 72 `PARTIAL`, and 9
  `NOT_STARTED`;
- all 144 source task executions are `NOT_RUN`;
- all 144 task evidence states are `NONE`;
- all four exact dependency Skills are `UNRESOLVED`;
- external evidence is `NOT_RUN`; and
- production certification is `NOT_CERTIFIED`.

Current V77/V77.1/V77.2 qualification is `NOT_RUN`. The historical V73 local
receipt does not cover the current migration bytes, Java bindings, or tests.

These documents and source files are implementation artifacts. A successful
local command is engineering evidence only and must not silently rewrite those
states.

## Bounded local commands

The smallest repository-owned structural checks are:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tooling/validate_multitenant_task_finops_runtime.py --repo-root .
PYTHONDONTWRITEBYTECODE=1 python3.11 -m unittest discover -s tests/multitenant-task-finops -p 'test_*.py'
```

Focused Java policy and API checks, when the Maven dependency graph is already
available, are:

```sh
mvn -B -ntp -pl modules/workflow -am -Dtest=TaskFinopsPolicyTest,TaskFinopsPortTest,TaskFinopsAdmissionPolicyTest,TaskFinopsProgressBatchTest,CheckpointForkPolicyTest,TenantLifecyclePolicyTest,TaskFinopsFeatureRolloutTest,PaymentSettlementReconcilerTest,TaskFinopsAnalyticsTest,TaskFinopsAnalyticsServiceTest,TaskFinopsAnalyticsExportTest,WorkloadAwareSchedulerTest,TaskFinopsModelCacheAnalyticsTest -Dsurefire.failIfNoSpecifiedTests=false test
mvn -B -ntp -pl modules/persistence -am -Dtest=TaskFinopsOperationsMigrationContractTest -Dsurefire.failIfNoSpecifiedTests=false test
mvn -B -ntp -pl apps/control-plane -am -Dtest=TaskFinopsControllerTest,TaskFinopsOperationsControllerTest -Dsurefire.failIfNoSpecifiedTests=false test
```

The finance semantics source contract and the dedicated disposable PostgreSQL
runtime fixture are:

```sh
mvn -o -pl modules/persistence -am -Dtest=TaskFinopsFinancialSemanticsContractTest -Dsurefire.failIfNoSpecifiedTests=false test
mvn -o -pl modules/persistence -am -Dtest=MultitenantTaskFinopsRuntimeIntegrationTest -Dsurefire.failIfNoSpecifiedTests=false test
```

The integration fixture uses exact image tag `postgres:17.5-alpine`. A current
rerun would have to apply the complete Flyway estate through V77.2 and exercise
the V77/V77.1/V77.2 boundaries in addition to canonical identity binding, the
account-wide three-slot limit, generation fencing, DB-authoritative runner
capabilities, progress/ETA monotonicity, pause completion, slot release, and
same-organization cross-account negatives. It must report zero skipped tests;
otherwise it is not current local runtime evidence.

## Historical bounded result

On 2026-08-24, the V73 task-scoped local qualification completed with 56
passing tests and zero failures, errors, or required skips:

- 31 focused Java workflow, persistence-contract, principal, and controller
  tests;
- one disposable PostgreSQL 17.5 integration fixture, after Flyway applied all
  65 discovered migrations through V73; and
- 24 Python runtime/inventory/boundary validation tests.

That receipt is retained as historical, digest-bound, self-attested local
engineering evidence only. It does not cover the current V77, V77.1, or V77.2
migrations, their new Java/SQL tests, or the current implementation bindings.
Current V77 qualification is `NOT_RUN`. The old receipt also does not execute
any of the 144 product task declarations, apply V100-V102, resolve the four
external dependency Skills, supply independent holdout or representative-
workload evidence, or change production certification.

The existing PostgreSQL/Testcontainers aggregate check can apply all discovered
Flyway migrations to disposable PostgreSQL:

```sh
mvn -B -ntp -pl modules/persistence -am -Dtest=FlywayMigrationTest -Dsurefire.failIfNoSpecifiedTests=false test
```

`FlywayMigrationTest` is disabled without Docker and currently covers the whole
migration estate. A pass with a skipped container is not evidence, and a whole-
estate migration pass alone is not sufficient evidence for high-contention
multi-replica slot races, production-role RLS, lease-loss race campaigns,
correction approval governance, or provider financial reconciliation. Those
remain separate evidence obligations even when the dedicated fixture passes.

## Receipt requirements

No command may change a source task from `NOT_RUN` without a task-specific,
content-addressed result receipt that records at least:

- exact task ID and implementation digest;
- commit, environment, database/runner versions, fixture digest, and command;
- start/end timestamps, exit code, test totals, and zero skipped required tests;
- raw logs or traces plus referenced database/object evidence;
- authorization, cleanup result, executor, and a distinct verifier where the
  task requires independent evidence; and
- explicit mapping to each acceptance assertion and negative case.

Python validation is structural. Java unit tests are deterministic local policy
evidence. A real disposable PostgreSQL run is local database engineering
evidence. None is Temporal replay, provider billing, invoice reconciliation,
cash settlement, independent field evidence, deployment, or certification.

Temporal worker/server replay and outage evidence remains unavailable under the
unresolved `elmos-temporal-task-reliability` dependency. Provider, invoice,
payment, external verifier, and production gates remain `NOT_RUN`; the maximum
honest current product state remains `NOT_CERTIFIED`.
