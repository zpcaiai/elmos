# First 40 Implementation Tasks

These tasks create the minimum truthful vertical slice before expanding dashboards or pricing models.

| Order | Task ID | Skill | Task |
|---:|---|---|---|
| 1 | `ELMOS-MTF-001-T01` | `elmos-multitenant-task-finops-orchestrator` | Scan the target repository and locate identity, task, workflow, runner, event, storage, billing, and analytics boundaries. |
| 2 | `ELMOS-MTF-001-T02` | `elmos-multitenant-task-finops-orchestrator` | Create a requirement-to-component gap matrix and mark existing, reusable, conflicting, and missing implementation. |
| 3 | `ELMOS-MTF-001-T03` | `elmos-multitenant-task-finops-orchestrator` | Freeze domain names, state machine, identifiers, idempotency keys, event names, and financial terms. |
| 4 | `ELMOS-MTF-001-T04` | `elmos-multitenant-task-finops-orchestrator` | Select the authoritative storage owner for every persistent data type and prohibit dual truth. |
| 5 | `ELMOS-MTF-001-T05` | `elmos-multitenant-task-finops-orchestrator` | Plan backward-compatible schema migrations and rollback/roll-forward procedures. |
| 6 | `ELMOS-MTF-001-T06` | `elmos-multitenant-task-finops-orchestrator` | Define the first production-shaped vertical slice and its fixtures. |
| 7 | `ELMOS-MTF-001-T07` | `elmos-multitenant-task-finops-orchestrator` | Sequence dependent skills and assign evidence owners. |
| 8 | `ELMOS-MTF-001-T08` | `elmos-multitenant-task-finops-orchestrator` | Define environment-specific feature flags and safe rollout order. |
| 9 | `ELMOS-MTF-001-T09` | `elmos-multitenant-task-finops-orchestrator` | Integrate runtime ETA reporting with queue, execution, model, validation, transfer, and recovery time. |
| 10 | `ELMOS-MTF-001-T10` | `elmos-multitenant-task-finops-orchestrator` | Track implementation status in a stable task matrix. |
| 11 | `ELMOS-MTF-001-T11` | `elmos-multitenant-task-finops-orchestrator` | Run all package and repository validation gates. |
| 12 | `ELMOS-MTF-001-T12` | `elmos-multitenant-task-finops-orchestrator` | Generate the final execution report with known limitations and waivers. |
| 13 | `ELMOS-MTF-002-T01` | `elmos-tenant-identity-rls` | Define OIDC claims and membership resolution rules. |
| 14 | `ELMOS-MTF-002-T02` | `elmos-tenant-identity-rls` | Remove all trust in client-provided tenant headers. |
| 15 | `ELMOS-MTF-002-T03` | `elmos-tenant-identity-rls` | Define transaction-local identity context propagation. |
| 16 | `ELMOS-MTF-002-T04` | `elmos-tenant-identity-rls` | Create non-superuser database roles and grants. |
| 17 | `ELMOS-MTF-002-T05` | `elmos-tenant-identity-rls` | Enable and force RLS on all tenant-scoped task tables. |
| 18 | `ELMOS-MTF-002-T06` | `elmos-tenant-identity-rls` | Create account-owner policies for global concurrency slots. |
| 19 | `ELMOS-MTF-002-T07` | `elmos-tenant-identity-rls` | Add admin and workflow-service access through explicit least-privilege paths. |
| 20 | `ELMOS-MTF-002-T08` | `elmos-tenant-identity-rls` | Classify task inputs, outputs, logs, prompts, usage, and revenue fields. |
| 21 | `ELMOS-MTF-002-T09` | `elmos-tenant-identity-rls` | Implement encryption-key references and log redaction. |
| 22 | `ELMOS-MTF-002-T10` | `elmos-tenant-identity-rls` | Audit all privileged task and finance operations. |
| 23 | `ELMOS-MTF-002-T11` | `elmos-tenant-identity-rls` | Add tenant export, retention, and deletion workflows. |
| 24 | `ELMOS-MTF-002-T12` | `elmos-tenant-identity-rls` | Execute cross-tenant, confused-deputy, and BYPASSRLS tests. |
| 25 | `ELMOS-MTF-003-T01` | `elmos-account-concurrency-admission` | Define slot-consuming and non-slot-consuming task states. |
| 26 | `ELMOS-MTF-003-T02` | `elmos-account-concurrency-admission` | Implement three durable account slot rows. |
| 27 | `ELMOS-MTF-003-T03` | `elmos-account-concurrency-admission` | Implement atomic slot claim with row locking and lease generation. |
| 28 | `ELMOS-MTF-003-T04` | `elmos-account-concurrency-admission` | Implement generation-safe slot renewal and release. |
| 29 | `ELMOS-MTF-003-T05` | `elmos-account-concurrency-admission` | Implement idempotent task submission. |
| 30 | `ELMOS-MTF-003-T06` | `elmos-account-concurrency-admission` | Queue fourth and later tasks without executing them. |
| 31 | `ELMOS-MTF-003-T07` | `elmos-account-concurrency-admission` | Promote queued tasks after terminal, paused, or safely reconciled slot release. |
| 32 | `ELMOS-MTF-003-T08` | `elmos-account-concurrency-admission` | Enforce tenant active-task, queued-task, and resource-unit quotas. |
| 33 | `ELMOS-MTF-003-T09` | `elmos-account-concurrency-admission` | Expose concurrency status and queue position APIs. |
| 34 | `ELMOS-MTF-003-T10` | `elmos-account-concurrency-admission` | Publish admission and slot lifecycle events. |
| 35 | `ELMOS-MTF-003-T11` | `elmos-account-concurrency-admission` | Add stale-slot reaping and reconciliation. |
| 36 | `ELMOS-MTF-003-T12` | `elmos-account-concurrency-admission` | Run high-contention race tests across multiple API replicas. |
| 37 | `ELMOS-MTF-004-T01` | `elmos-workload-aware-scheduler` | Define workload classes and resource-unit weights. |
| 38 | `ELMOS-MTF-004-T02` | `elmos-workload-aware-scheduler` | Estimate root-task and node-level resource demand. |
| 39 | `ELMOS-MTF-004-T03` | `elmos-workload-aware-scheduler` | Create workload-specific Temporal task queues. |
| 40 | `ELMOS-MTF-004-T04` | `elmos-workload-aware-scheduler` | Configure bounded worker concurrency per queue. |
