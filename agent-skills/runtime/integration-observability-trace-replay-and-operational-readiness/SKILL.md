---
name: integration-observability-trace-replay-and-operational-readiness
description: Establish cross-platform trace, message lineage, lag, queue depth, DLQ, partner acknowledgement, replay controls, SLOs, alerts, and runbooks. Use when validating operational readiness or authorizing a bounded message replay across API, MQ, Kafka, RabbitMQ, B2B, and workflows.
---

# Integration Observability and Replay

## Correlate the journey

Link trace ID, span ID, message ID, correlation ID, causation ID, event ID, business journey ID, partner transfer ID, and process instance ID. Build lineage from producer through broker, route, transformer, consumer, and side effect.

Monitor publish/consume rate, queue depth, lag, oldest message, redelivery, retry, DLQ, partition skew, connections, channels, disk, memory, API errors/latency/auth, transfer duration, MDN, functional/business acknowledgements, certificates, and workflow incidents.

## Control replay

Require an approved source, range, schema, consumer, idempotency boundary, side-effect policy, rate, ordering, checkpoint, and stop condition. Track PLANNED, AUTHORIZED, RUNNING, PAUSED, COMPLETED, FAILED, and RECONCILED.

Block broad cutover without dashboards, alerts, owner, runbook, capacity, backup/DR, DLQ handling, lag limits, certificate monitoring, partner contacts, and replay procedure.
