---
name: serverless-function-and-event-driven-modernizer
description: Modernize eligible web, batch, and event workloads into functions, serverless containers, consumers, scheduled functions, workflows, edge functions, or inference functions. Use for serverless eligibility and validation.
---

# Serverless Modernizer

## Eligibility workflow

1. Measure startup, duration, memory, CPU, concurrency, state, files, networking, connections, events, idempotency, retry, license, and cost.
2. Reject or require refactoring for local durable files, in-memory sessions, singleton state, local schedulers, local locks, long runtimes, special hardware/networking, or incompatible licenses.
3. Choose function, serverless container, event consumer, scheduled function, workflow step, edge function, or model inference function deliberately.
4. Version event source, type, schema, ID, time, subject, trace, retry, DLQ, delivery, and ordering contracts.
5. Validate cold start, first request, connection warm-up, caches, JIT/model load, minimum instances, scale-to-zero, and cost against SLOs.
6. Bound per-instance and maximum concurrency, queueing, backpressure, downstream capacity, and database connections.
7. Require idempotency, retryable error classification, maximum attempts, backoff, poison-event handling, DLQ, and controlled replay.
8. Validate each immutable revision in an emulator or approved provider sandbox.

Do not fragment a distributed business transaction into unobservable functions. Return serverless-ineligible or pilot-required when evidence is incomplete.

