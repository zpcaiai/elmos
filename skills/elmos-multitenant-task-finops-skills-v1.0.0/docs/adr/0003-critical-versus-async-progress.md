# ADR-0003 — Split critical persistence from asynchronous progress

## Status
Accepted.

## Context
Persisting every heartbeat/log line synchronously harms task throughput, but asynchronous state/checkpoint recording can make recovery and billing incorrect.

## Decision
Persist critical transitions, terminal node states, checkpoints, receipts, artifact manifests, usage, revenue, and audit durably before acknowledgement. Batch heartbeats, fine progress, logs, telemetry, and analytical projections asynchronously.

## Consequences
- Critical and non-critical event types must be explicit.
- Buffers must be bounded and flush at safe lifecycle points.
- UI progress is eventually consistent; business/financial truth is durable.
