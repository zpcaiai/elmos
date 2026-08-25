# ELMOS Spring Golden Route engine

This dependency-free Python 3.12 engine is a bounded, local control plane for
the 196 contracts imported from
`elmos-spring-golden-route-commercial-skills-v2.0.0.zip`.

It validates the repository manifest, compiled contracts, archive digest,
installed Skill files, interfaces, contract references, counts, identities,
and dependency DAG before exposing a registry. Every Skill has a distinct
callable. Those callables support only:

- `describe`: return the immutable imported contract and its conservative
  evidence boundary.
- `plan`: return a `DRAFT_ONLY` blueprint. Source discovery, FCM extraction,
  generation, builds, startup, behavior checks, security checks, holdout runs,
  customer evidence, and external verification remain `NOT_RUN`.

The engine never runs Spring, build tools, repository hooks, provider APIs, or
repository writes. Requests for execution or side effects fail with
`EXTERNAL_ADAPTER_REQUIRED`. Local dispatch can be reported only as
`LOCAL_EXECUTED_SELF_ATTESTED`; it is not domain runtime evidence.

The SQLite store records run state, optimistic transitions, idempotency,
append-only hash-chained events, and digest-bound local evidence. Because the
local engine has no independent authorization trust store, its strongest
possible decision is `LOCAL_HANDOFF_PREPARED` (below
`READY_FOR_EXTERNAL_GATE`). It always reports
customer/external evidence as `NOT_RUN` and certification as `NOT_CERTIFIED`.

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
