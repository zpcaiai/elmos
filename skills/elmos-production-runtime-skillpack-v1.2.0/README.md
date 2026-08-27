# Elmos Production Repository Execution OS Skill Pack v1.2.0

This package consolidates the full Elmos design for large-scale concurrent repository execution and real-time prepaid billing.

It covers four first-class business lines:

1. Spring legacy modernization.
2. Whole-repository cross-language conversion.
3. Multi-language project generation.
4. SQL dialect / SQL routine conversion.

All four share one execution kernel.

## Core runtime

```text
Tenant / Account
    |
    +-- Billing Account / Wallet / Quota
    |
    +-- Project
          |
          +-- Immutable Repository Snapshot
          +-- Job
                |
                +-- Stage DAG
                      |
                      +-- WorkItem
                            |
                            +-- DispatchIntent
                            +-- Attempt
                                  |
                                  +-- Lease / Fence
                                  +-- ModelCall
                                  |     |
                                  |     +-- UsageMeterEvent*
                                  |     +-- FinalUsageEvent
                                  |             |
                                  |             +-- Settlement
                                  |
                                  +-- ToolCall
                                  +-- Checkpoint
                                  +-- Artifact / ChangeSet
```

## Key properties

- Repository-scale DAG execution.
- Parallel work across many tenants and projects.
- Crash recovery and resumability.
- Fencing against stale workers.
- Durable dispatch Saga; no cross-service XA transaction.
- Prepaid credit reservation before billable execution.
- Streaming token/credit metering during model calls.
- Provider pricing and customer commercial pricing separated.
- Top-up, settlement, refund and adjustment accounting.
- Immutable ledger plus double-entry journal.
- Real-time progress / ETA / token / credit projections.
- Tenant isolation and service-level database ownership.
- Redis loss never loses durable work or money state.

## Production label

This package is an implementation-grade production candidate. A deployment may be called production-certified only after its own CI, Testcontainers, load, chaos, backup/PITR and reconciliation gates pass in the target environment.
