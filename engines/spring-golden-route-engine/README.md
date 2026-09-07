# ELMOS Spring Golden Route engine

This dependency-free Python 3.12 engine is a bounded, local control plane for
the 196 contracts imported from
`elmos-spring-golden-route-commercial-skills-v2.0.0.zip`.

It validates the repository manifest, compiled contracts, archive digest,
installed Skill files, interfaces, contract references, counts, identities,
the raw foundation Batch graph (`01` through `10`), its exact normalized
identity map (`F01` through `F10`), the commercial Batch graph, and the Skill
dependency DAG before exposing a registry. Every Skill has a distinct callable.
Those callables support only:

- `describe`: return the immutable imported contract and its conservative
  evidence boundary.
- `plan`: return a `DRAFT_ONLY` blueprint. Source discovery, FCM extraction,
  generation, builds, startup, behavior checks, security checks, holdout runs,
  customer evidence, and external verification remain `NOT_RUN`.

Describe and plan responses use `elmos.spring-golden-route.response.v2` and
expose the contract's normalized `batch` plus its direct `batch_dependencies`.
Raw foundation IDs such as `01` never appear as contract Batch identities.

The engine never runs Spring, build tools, repository hooks, provider APIs, or
target-repository writes. Requests for execution or side effects fail with
`EXTERNAL_ADAPTER_REQUIRED`. Local dispatch can be reported only as
`LOCAL_EXECUTED_SELF_ATTESTED`; it is not domain runtime evidence.

## Agent Step Budget domain runtime

`elmos_spring_golden_route.step_budget.StepBudgetStore` is a separate exact
local runtime for `FOUNDATION-06-agent-step-budget`. It does not promote the
other imported contracts and does not change the package-level
`SPECIFICATION_IMPORTED` decision. Its machine-readable request, response, and
error schemas are shipped beside the Python module.

The runtime provides `admit`, `reserve`, `settle`, `status`, `cancel`, and
`audit`. A step is durably reserved before execution, only one unsettled step
is allowed per Agent/task, and an `UNKNOWN` outcome blocks retry until an
authorized reconciliation path exists. Complexity and expected cost produce
an effective step/turn cap bounded by hard, token, and micro-USD limits.
Optimistic versions, idempotency identities, immutable operation receipts,
append-only hash-chained events, state-to-chain binding, and restart recovery
are enforced in SQLite.

Every operation requires a short-lived authorization object bound to the exact
tenant/project/run/task/Agent scope and permission. `StepBudgetStore` has no
permissive verifier: callers must inject a trusted authorization-verifier
adapter, and verifier absence/error/deny fails before state access. Opaque
authorization tokens are never persisted. The runtime only grants a local
step permit; it does not execute the step or certify its external outcome.
Customer, independent, and certification evidence therefore remain `NOT_RUN`
and `NOT_CERTIFIED`.

The SQLite store records run state, optimistic transitions, idempotency,
append-only hash-chained events, and digest-bound local evidence. Because the
local engine has no independent authorization trust store, its strongest
possible local status is `LOCAL_HANDOFF_PREPARED`; the readiness decision stays
`BLOCKED` until an external authorized verifier runs. It always reports
customer/external evidence as `NOT_RUN` and certification as `NOT_CERTIFIED`.
Every command that reads or mutates an existing run reloads the exact repository
catalog and registry, then redispatches the complete stored plan before access.
Library callers must likewise provide that registry; an unbound store may only
initialize or validate the SQLite schema.

## Run

From this directory:

```bash
PYTHONPATH=src python -m elmos_spring_golden_route validate-catalog \
  --repo-root ../..
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'
```

Invoke a Skill with canonical request data:

```bash
PYTHONPATH=src python -m elmos_spring_golden_route invoke \
  --repo-root ../.. --request request.json
```

The request object has exactly these top-level fields:

```json
{
  "actor_id": "actor-1",
  "idempotency_key": "idem-1",
  "input": {
    "constraints": ["No production access"],
    "objective": "Produce a bounded migration plan",
    "requested_outputs": [],
    "source": {
      "commit": "1111111111111111111111111111111111111111",
      "framework": "spring-boot",
      "version": "2.7.18"
    },
    "target": {
      "commit": "2222222222222222222222222222222222222222",
      "framework": "spring-boot",
      "version": "3.3.4"
    }
  },
  "operation": "plan",
  "project_id": "project-1",
  "run_id": "run-1",
  "schema_version": "elmos.spring-golden-route.request.v1",
  "skill_name": "lossless-semantic-ir",
  "task_id": "task-1",
  "tenant_id": "tenant-1"
}
```

Unknown fields, duplicate JSON keys, oversized values, invalid identifiers,
unknown Skills, and unsupported operations are rejected. `input` must be empty
for `describe`; `plan` accepts only `objective`, `source`, `target`,
`constraints`, and `requested_outputs` with bounded values.

## SQLite state schema

The durable store uses schema ID `elmos.spring-golden-route.run-store`, schema
version `1`, `PRAGMA user_version=1`, and a digest of its exact table/trigger
contract. Validation compares normalized table and trigger SQL, column types and
nullability, primary/unique index semantics, checks, foreign keys, and trigger
bodies. Existing compatible databases are opened without DDL changes. Missing,
older, newer, or drifted schemas fail with
`STATE_SCHEMA_MIGRATION_REQUIRED`; this engine performs no automatic migration.
Migration requires a separately reviewed, backup-aware migration tool and is
outside this bounded runtime.
