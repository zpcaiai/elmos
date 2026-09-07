# Architecture Overview

## Bounded contexts

| Context | Owns |
|---|---|
| identity | tenant, account, membership |
| project | repository, project, immutable snapshot |
| semantic | modules, files, symbols, dependency graph, SQL graph |
| orchestration | jobs, stages, work items, DAG dependencies |
| runtime | dispatch intents, attempts, leases, workers, environments, checkpoints |
| artifact | artifacts, patches, change sets |
| validation | validation runs, cases, defects, repairs |
| ai_usage | model/tool calls, model-call receipts |
| billing | wallets, idempotency, top-ups, pricing, meter events, final usage, ledger, journals |
| observability | durable project events, outbox, projections |

## No four separate products

The four business lines differ by Workload Pack, not by runtime architecture.

Future tasks such as `.NET Framework -> .NET`, `Vue2 -> Vue3`, security remediation and monolith decomposition should reuse the same kernel.
