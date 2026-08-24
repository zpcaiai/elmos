# Skill Index

| ID | Skill | Layer | Risk | Dependencies | Tasks |
|---|---|---|---|---|---:|
| `ELMOS-MTF-001` | `elmos-multitenant-task-finops-orchestrator` | orchestration | critical | `elmos-architecture-contract-governance`, `elmos-identity-tenant-security`, `elmos-temporal-task-reliability`, `elmos-observability-finops` | 12 |
| `ELMOS-MTF-002` | `elmos-tenant-identity-rls` | security | critical | `elmos-multitenant-task-finops-orchestrator` | 12 |
| `ELMOS-MTF-003` | `elmos-account-concurrency-admission` | runtime-control | critical | `elmos-tenant-identity-rls` | 12 |
| `ELMOS-MTF-004` | `elmos-workload-aware-scheduler` | scheduling | high | `elmos-account-concurrency-admission` | 12 |
| `ELMOS-MTF-005` | `elmos-task-lifecycle-temporal` | workflow | critical | `elmos-workload-aware-scheduler` | 12 |
| `ELMOS-MTF-006` | `elmos-task-progress-journal` | observability | high | `elmos-task-lifecycle-temporal` | 12 |
| `ELMOS-MTF-007` | `elmos-checkpoint-recovery` | reliability | critical | `elmos-task-lifecycle-temporal`, `elmos-task-progress-journal` | 12 |
| `ELMOS-MTF-008` | `elmos-task-io-artifact-archive` | storage | high | `elmos-task-progress-journal`, `elmos-checkpoint-recovery` | 12 |
| `ELMOS-MTF-009` | `elmos-usage-metering-cost-ledger` | finops | critical | `elmos-task-io-artifact-archive` | 12 |
| `ELMOS-MTF-010` | `elmos-revenue-margin-ledger` | billing | critical | `elmos-usage-metering-cost-ledger` | 12 |
| `ELMOS-MTF-011` | `elmos-task-financial-analytics` | analytics | high | `elmos-usage-metering-cost-ledger`, `elmos-revenue-margin-ledger` | 12 |
| `ELMOS-MTF-012` | `elmos-concurrency-recovery-finops-certification` | quality | critical | `elmos-account-concurrency-admission`, `elmos-workload-aware-scheduler`, `elmos-task-lifecycle-temporal`, `elmos-task-progress-journal`, `elmos-checkpoint-recovery`, `elmos-task-io-artifact-archive`, `elmos-task-financial-analytics` | 12 |

## Invocation

Use the orchestrator for the full program:

```text
$elmos-multitenant-task-finops-orchestrator
```

Use the certification skill before any production-ready claim:

```text
$elmos-concurrency-recovery-finops-certification
```
