---
name: async-generator-and-cancellation-lowering
description: Lower coroutine/task/future/promise/callback, generator, async stream, scheduler, timeout, backpressure, and cancellation semantics. Use for any async or suspended callable.
---
# Async, Generator, and Cancellation Lowering
Read `../references/lowering-v1.md`. Profile cold/hot and start timing, single/stream result, await order, scheduler/context, cancellation, timeout, backpressure, blocking, completion and error channel. Propagate explicit target cancellation tokens through internal calls without silently breaking public APIs.

Do not make async synchronous, block to imitate await, materialize generators/async streams by default, lose cancellation, conflate timeout with cancellation, or wrap multi-shot/reentrant callbacks as one task. Record scheduler/context changes and preserve lazy resource lifetimes.
