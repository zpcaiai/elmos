---
name: async-exception-resource-contract-emitter
description: Emit target async, error, cancellation, resource, disposal, and concurrency contracts. Use for skeleton signatures with nontrivial runtime semantics.
---
# Async Exception Resource Contract Emitter
Read `../references/skeleton-v1.md`. Preserve source/target async kind, awaitable result, cancellation/timeout/context, exception hierarchy/error channel/filter, close/dispose/async-dispose/ownership/cleanup, shared state, locks/atomics/scheduler/event-loop/blocking. Never downgrade async to sync, rejection to return, discard cancellation, merge sync/async disposal, or approximate unmappable locks without a blocking strategy.
