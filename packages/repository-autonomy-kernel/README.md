# Elmos Repository Autonomy Kernel

This package is the repository-owned implementation of the 31 Skills in
`elmos-repository-autonomy-kernel-v2.0.0`. It is deliberately provider-neutral:
the local runtime performs deterministic planning, authorization, persistence,
analysis and evidence work. Provider, SCM, database, object-store and cluster
effects must be supplied through an explicitly authorized adapter.

## Run locally

```bash
PYTHONPATH=src python -m elmos_repository_autonomy.cli catalog
PYTHONPATH=src python -m elmos_repository_autonomy.cli dispatch \
  task-spec-delta-compiler '{"requirements":{"objective":"add health endpoint"}}'
PYTHONPATH=src python -m elmos_repository_autonomy.cli serve --db /tmp/elmos-autonomy.db
PYTHONPATH=src python -m elmos_repository_autonomy.cli local-conformance
PYTHONPATH=src python -m elmos_repository_autonomy.cli matrix --tenant local
# Validate exact external bindings without executing them:
PYTHONPATH=src python -m elmos_repository_autonomy.cli external-preflight \
  --manifest /approved/path/external-qualification-manifest.json
# After an approved PostgreSQL service is configured and before serving:
PYTHONPATH=src python -m elmos_repository_autonomy.cli postgres-migrate \
  --service elmos-autonomy --operator migration-operator \
  --authorization-receipt "$APPROVED_RECEIPT_DIGEST"
PYTHONPATH=src python -m elmos_repository_autonomy.cli serve \
  --db /var/lib/elmos-autonomy/autonomy.sqlite \
  --postgres-control-service elmos-autonomy
```

The HTTP service exposes `/livez`, `/readyz`, `/metrics`, `/version`,
`/v1/skills`, `/v1/skills/{skill}:run`, `/v1/runs/{run_id}` and
`/v1/runs/{run_id}/events`, plus the lifecycle and integration endpoints
`/v2/runs`, `/v2/runs/{run_id}/{pause|resume|cancel}`, `/v2/tool-calls`,
`/v2/packages`, `/v2/adapters/{adapter}/conformance`, `/v2/arena/runs`,
`/v2/gym/suites/{suite}/run`, `/v2/external/operations`,
`/v2/certification/{evidence|matrix|evaluate}`, `/v2/golden-routes/{route}/evaluate`
and `/v2/customer-acceptance`. Mutating requests require verified tenant and
account headers; request payloads cannot manufacture execution authority.

## Production boundary

SQLite is a deterministic local backend for contract and integration tests.
`sql/migrations/V001__...sql` through `V006__...sql` are the ordered PostgreSQL
target migrations; `sql/001_autonomy_kernel.sql` is the single-file equivalent
for controlled bootstrap environments. The optional `postgres` extra supplies
the PostgreSQL driver; migration and disaster-recovery APIs use service references
so credentials are not placed in command arguments. The package does not claim PostgreSQL,
object-storage, event-bus, provider, Kubernetes, customer or
independent-certification evidence merely because local tests pass.
Unknown tools, missing authority, stale fencing, partial results, unverified
findings and missing deployment evidence fail closed.

Approved external implementations can be attached through `CommandBinding`
and the PostgreSQL, SCM, S3, Event Bus, Secrets Broker, Kubernetes,
independent-verifier and seven-provider command transports. A binding uses an
absolute non-symlink executable, SHA-256 pin,
explicit protocol allowlist, environment-variable references, bounded
canonical JSON input/output, no shell, process-group timeout and digest-only
execution evidence. The manifest contract is
[`external-qualification-manifest.schema.json`](contracts/external-qualification-manifest.schema.json).
`external-preflight` only proves that bindings are structurally ready for a
separately authorized run; it always leaves external evidence `NOT_RUN`,
E1-E5 `NOT_RUN`, certification `NOT_CERTIFIED`, and P05 unissued.

外部能力的补全路线见
[EXTERNAL_COMPLETION_PLAN.md](docs/EXTERNAL_COMPLETION_PLAN.md)，逐项测试矩阵见
[EXTERNAL_TEST_PLAN.md](docs/EXTERNAL_TEST_PLAN.md)。两份计划都保留真实 SCM、S3、Event Bus、Secrets Broker、Provider、Kubernetes、客户仓库、独立验收和 E1-E5 认证的 `NOT_RUN/NOT_CERTIFIED` 边界。
