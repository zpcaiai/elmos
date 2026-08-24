# Implementation Deliverables

Every target-repository implementation must produce the following durable artifacts.

## Control plane

- identity and membership contract;
- account concurrency admission service;
- queue and scheduler policy;
- task/run/node/attempt state implementation;
- pause/resume/cancel/retry APIs;
- SSE/WebSocket progress replay;
- tenant and account concurrency UI.

## Persistence

- versioned PostgreSQL migrations;
- runtime database role and grant scripts;
- RLS attack tests using non-superuser roles;
- outbox and inbox-dedup implementation;
- object-store manifest, lifecycle and legal-hold policy;
- backup, restore, export and deletion procedures.

## Workflow and runner

- Temporal workflows, activities, Signals/Updates and Search Attributes;
- deterministic workflow startup contract;
- workflow replay/versioning tests;
- runner lease, heartbeat, renewal, cancellation and completion protocol;
- workload-specific sandbox and egress policy;
- checkpoint compatibility and recovery implementation.

## FinOps and commercial accounting

- model/provider usage adapters;
- compute/storage/network metering;
- versioned price book and FX snapshot mechanism;
- cost budget, reserve and alert path;
- immutable revenue ledger and task allocation;
- provider invoice and payment settlement reconciliation;
- task, account, tenant and platform financial projections.

## Quality and evidence

- unit, contract, integration, E2E, load, chaos and security tests;
- queue fairness and three-slot race reports;
- checkpoint/recovery and ambiguous-side-effect reports;
- financial duplicate/missing/correction reconciliation reports;
- OpenTelemetry dashboards, SLOs, alerts and runbooks;
- `EXECUTION_REPORT.md` and `evidence-bundle.json` bound to the repository commit.
