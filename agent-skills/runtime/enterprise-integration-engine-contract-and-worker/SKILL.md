---
name: enterprise-integration-engine-contract-and-worker
description: Implement and operate the ELMOS Enterprise Integration worker contract for ESB, MQ, Kafka, RabbitMQ, API Gateway, EDI, MFT, and workflow modernization. Use for capability discovery, leased runner routing, fail-closed execution, tenant-scoped jobs, or provider adapter work.
---

# Enterprise Integration Engine

## Operate the worker

1. Expose `ELMOS_ENTERPRISE_INTEGRATION` capabilities and `/engine/v1` scan, plan, execute-step, validate, job, and cancel operations.
2. Route every external product through a versioned Adapter. Keep adapters `NOT_CONFIGURED` until an approved environment supplies a short-lived credential lease and allowlisted network scope.
3. Make discovery read-only. Bind every job to organization, immutable snapshot, workspace, correlation ID, and idempotency key.
4. Return `NOT_RUN`, no evidence, and a stable error code when a provider, permission, test environment, partner authorization, or replay approval is absent.

## Enforce authority

- Never purge production queues, reset offsets, delete topics, change partner certificates, replay production messages, create public routes, switch producers, or accept message loss.
- Require independent production approval for broker, gateway, partner, workflow, bridge, replay, and cutover changes.
- Keep the Worker unable to modify quality, cutover, or decommission decisions.

## Produce

Emit only evidence-backed estate, contract, route, delivery, validation, replay, and cutover artifacts through the shared ELMOS Evidence protocol. Record adapter version, resource scope, sanitized logs, external status, and cleanup result.

## Accept

Accept only when the Engine deploys independently, providers remain replaceable, discovery is read-only, credentials are short lived, jobs are tenant scoped, and missing external execution cannot appear as success.
